"""Command-execution abstraction for external orchestration commands.

Classifies commands as Discovery Operations or Lifecycle Mutations and
applies phase-aware timeout, retry with jittered backoff, stdout/stderr
capture, and structured error reporting.

Agent Harness execution remains governed by harness-specific timeout
configuration and does NOT use this module's defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random
import subprocess
import time
from typing import Protocol


class CommandPhase(Enum):
    """Classification of a command's operational impact."""

    DISCOVERY = "discovery"
    LIFECYCLE_MUTATION = "lifecycle_mutation"


@dataclass(frozen=True)
class CommandResult:
    """Structured result of a command execution including diagnostics."""

    command: tuple[str, ...]
    phase: CommandPhase
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    retries_attempted: int
    cwd: str | None = None
    diagnostics: str | None = None

    @property
    def succeeded(self) -> bool:
        """True when the final attempt exited zero and did not time out."""
        return self.exit_code == 0 and not self.timed_out


class CommandError(Exception):
    """Raised when a command fails after exhausting all retries."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        parts = [f"Command failed (phase={result.phase.value})"]
        if result.timed_out:
            parts.append("timed out")
        parts.append(f"exit_code={result.exit_code}")
        parts.append(f"retries={result.retries_attempted}")
        if result.diagnostics:
            parts.append(result.diagnostics)
        cmd_str = " ".join(result.command)
        super().__init__(f"{' '.join(parts)}: {cmd_str}")


RetrySafetyCheck = callable  # (CommandResult) -> bool


class CommandExecutor:
    """Phase-aware command execution with timeout, retry, and jittered backoff.

    Discovery Operations
        Default timeout: 30 seconds.
        Default retries: 2 (for transient failures).
        Backoff: jittered, up to ~8 seconds.

    Lifecycle Mutations
        Default timeout: 120 seconds.
        Default retries: 1, **only** when a *retry_safety_check* callable
        is provided by the caller and returns True after a failed attempt.
        Without a safety check, mutations are never retried.
    """

    def __init__(
        self,
        *,
        discovery_timeout: float = 30.0,
        discovery_retries: int = 2,
        mutation_timeout: float = 120.0,
        mutation_retries: int = 1,
    ) -> None:
        self._discovery_timeout = discovery_timeout
        self._discovery_retries = discovery_retries
        self._mutation_timeout = mutation_timeout
        self._mutation_retries = mutation_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        command: tuple[str, ...],
        phase: CommandPhase,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        retry_safety_check: RetrySafetyCheck | None = None,
    ) -> CommandResult:
        """Execute *command* with phase-aware timeout and retry behaviour.

        Parameters
        ----------
        command:
            The command and its arguments as a tuple.
        phase:
            ``DISCOVERY`` or ``LIFECYCLE_MUTATION`` — selects defaults.
        cwd:
            Working directory for the subprocess.
        timeout:
            Per-attempt timeout in seconds.  Overrides the phase default.
        retries:
            Maximum number of *retries* (additional attempts after the
            first).  Overrides the phase default.
        retry_safety_check:
            For lifecycle mutations, a callable ``(CommandResult) -> bool``
            that must return ``True`` for a retry to be attempted.  Has no
            effect on discovery operations (they are always retried on
            transient failures).
        """
        max_retries: int
        per_attempt_timeout: float

        if phase is CommandPhase.DISCOVERY:
            per_attempt_timeout = timeout if timeout is not None else self._discovery_timeout
            max_retries = retries if retries is not None else self._discovery_retries
        else:
            per_attempt_timeout = timeout if timeout is not None else self._mutation_timeout
            max_retries = retries if retries is not None else self._mutation_retries

        return self._execute_with_retries(
            command=command,
            cwd=cwd,
            timeout=per_attempt_timeout,
            max_retries=max_retries,
            phase=phase,
            retry_safety_check=retry_safety_check,
        )

    def execute_discovery(
        self,
        command: tuple[str, ...],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> CommandResult:
        """Convenience wrapper — short-hand for ``execute(…, phase=DISCOVERY)``."""
        return self.execute(command, CommandPhase.DISCOVERY, cwd=cwd, timeout=timeout, retries=retries)

    def execute_mutation(
        self,
        command: tuple[str, ...],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        retry_safety_check: RetrySafetyCheck | None = None,
    ) -> CommandResult:
        """Convenience wrapper — short-hand for ``execute(…, phase=LIFECYCLE_MUTATION)``."""
        return self.execute(
            command,
            CommandPhase.LIFECYCLE_MUTATION,
            cwd=cwd,
            timeout=timeout,
            retries=retries,
            retry_safety_check=retry_safety_check,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_with_retries(
        self,
        *,
        command: tuple[str, ...],
        cwd: str | None,
        timeout: float,
        max_retries: int,
        phase: CommandPhase,
        retry_safety_check: RetrySafetyCheck | None = None,
    ) -> CommandResult:
        attempts = 0
        last_result: CommandResult | None = None

        for attempt in range(max_retries + 1):  # 1 initial + N retries
            if attempt > 0:
                # Jittered backoff: base = 2^attempt, max 8s,
                # jitter uniformly distributed in [0.5, 1.5] × base.
                base = min(2 ** attempt, 8.0)
                jitter = random.uniform(0.5, 1.5)
                wait = base * jitter
                time.sleep(wait)

            result = self._run_one(command=command, cwd=cwd, timeout=timeout, phase=phase)
            attempts += 1
            last_result = result

            if result.succeeded:
                return CommandResult(
                    command=command,
                    phase=phase,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    timed_out=False,
                    retries_attempted=attempts - 1,
                    cwd=cwd,
                    diagnostics=None,
                )

            # Determine if this failure is transient/retryable
            transient = _is_transient_failure(result)

            if phase is CommandPhase.DISCOVERY:
                if not transient:
                    # Non-transient failure — do not retry discovery ops
                    break
            else:
                # Lifecycle mutation
                if retry_safety_check is None or not retry_safety_check(result):
                    # Not safe to retry, or no safety check provided
                    break

        # All attempts exhausted — build diagnostic and return failure
        assert last_result is not None
        diag_parts: list[str] = []
        if last_result.timed_out:
            diag_parts.append(f"Command timed out after {timeout:.0f}s")
        elif last_result.exit_code != 0:
            diag_parts.append(f"Command exited with code {last_result.exit_code}")
        if last_result.stderr.strip():
            diag_parts.append(f"stderr: {last_result.stderr.strip()[:500]}")
        diagnostics = "; ".join(diag_parts) if diag_parts else None

        return CommandResult(
            command=command,
            phase=phase,
            stdout=last_result.stdout,
            stderr=last_result.stderr,
            exit_code=last_result.exit_code,
            timed_out=last_result.timed_out,
            retries_attempted=attempts - 1,
            cwd=cwd,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _run_one(
        *,
        command: tuple[str, ...],
        cwd: str | None,
        timeout: float,
        phase: CommandPhase,
    ) -> CommandResult:
        """Execute a single subprocess invocation and return a raw result."""
        timed_out = False
        exit_code: int
        stdout = ""
        stderr = ""

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout = exc.stdout or "" if exc.stdout else ""
            stderr = exc.stderr or "" if exc.stderr else ""
            if not stderr:
                stderr = f"Command timed out after {timeout:.0f}s"
        except OSError as exc:
            # FileNotFoundError, PermissionError, etc. — not retryable
            timed_out = False
            exit_code = -1
            stderr = str(exc)

        return CommandResult(
            command=command,
            phase=phase,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            retries_attempted=0,
            cwd=cwd,
            diagnostics=None,
        )


# ------------------------------------------------------------------
# Transient-failure heuristics
# ------------------------------------------------------------------

# Known transient failure patterns for git and gh CLI.
_TRANSIENT_STDERR_PATTERNS: tuple[str, ...] = (
    "Could not resolve host",
    "Failed to connect to",
    "Connection refused",
    "Connection reset",
    "Connection timed out",
    "Temporary failure in name resolution",
    "curl error",
    "Operation timed out",
    "fatal: unable to access",
    "fatal: the remote end hung up unexpectedly",
    "fatal: read error",
    "fatal: early EOF",
    "Remote connection dropped",
    "Unable to resolve",
    "Network is unreachable",
    "No route to host",
    "Gateway Time-out",
    "Service Unavailable",
    "rate limit",
)


def _is_transient_failure(result: CommandResult) -> bool:
    """Heuristic check: is this failure likely transient (network, timeout)? """
    if result.timed_out:
        return True

    combined = (result.stdout + " " + result.stderr).lower()
    for pattern in _TRANSIENT_STDERR_PATTERNS:
        if pattern.lower() in combined:
            return True
    return False
