"""Tests for command_executor.py — phase-aware command execution abstraction."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from rangkai.command_executor import (
    CommandError,
    CommandExecutor,
    CommandPhase,
    CommandResult,
    _is_transient_failure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(**overrides) -> CommandResult:
    """Build a CommandResult with sensible test defaults."""
    defaults = {
        "command": ("dummy",),
        "phase": CommandPhase.DISCOVERY,
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "retries_attempted": 0,
        "cwd": None,
        "diagnostics": None,
    }
    defaults.update(overrides)
    return CommandResult(**defaults)


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------

class TestCommandResult:
    def test_succeeded_zero_exit_no_timeout(self) -> None:
        r = _result(exit_code=0, timed_out=False)
        assert r.succeeded is True

    def test_succeeded_non_zero_exit(self) -> None:
        r = _result(exit_code=1, timed_out=False)
        assert r.succeeded is False

    def test_succeeded_timed_out(self) -> None:
        r = _result(exit_code=0, timed_out=True)
        assert r.succeeded is False

    def test_all_fields_present(self) -> None:
        r = _result(command=("git", "push"), phase=CommandPhase.LIFECYCLE_MUTATION,
                    stdout="ok\n", stderr="warn\n", exit_code=0, timed_out=False,
                    retries_attempted=1, cwd="/tmp", diagnostics="nothing")
        assert r.stdout == "ok\n"
        assert r.stderr == "warn\n"
        assert r.exit_code == 0
        assert not r.timed_out
        assert r.retries_attempted == 1
        assert r.cwd == "/tmp"
        assert r.diagnostics == "nothing"
        assert r.phase == CommandPhase.LIFECYCLE_MUTATION


# ---------------------------------------------------------------------------
# Successful execution
# ---------------------------------------------------------------------------

class TestSuccessfulExecution:
    def test_discovery_success(self) -> None:
        executor = CommandExecutor()
        result = executor.execute(
            ("echo", "hello"),
            CommandPhase.DISCOVERY,
        )
        assert result.succeeded
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.retries_attempted == 0
        assert result.phase == CommandPhase.DISCOVERY
        assert result.diagnostics is None

    def test_mutation_success(self) -> None:
        executor = CommandExecutor()
        result = executor.execute(
            ("echo", "world"),
            CommandPhase.LIFECYCLE_MUTATION,
        )
        assert result.succeeded
        assert result.exit_code == 0
        assert "world" in result.stdout
        assert result.phase == CommandPhase.LIFECYCLE_MUTATION

    def test_convenience_discovery(self) -> None:
        executor = CommandExecutor()
        result = executor.execute_discovery(("echo", "x"))
        assert result.succeeded
        assert result.phase == CommandPhase.DISCOVERY

    def test_convenience_mutation(self) -> None:
        executor = CommandExecutor()
        result = executor.execute_mutation(("echo", "y"))
        assert result.succeeded
        assert result.phase == CommandPhase.LIFECYCLE_MUTATION

    def test_stderr_captured(self) -> None:
        executor = CommandExecutor()
        result = executor.execute(("bash", "-c", "echo ok && echo err >&2"), CommandPhase.DISCOVERY)
        assert result.succeeded
        assert "ok" in result.stdout
        assert "err" in result.stderr


# ---------------------------------------------------------------------------
# Non-zero exit
# ---------------------------------------------------------------------------

class TestNonZeroExit:
    def test_discovery_non_zero_exit_not_retried(self) -> None:
        """Non-zero exit from a discovery command is NOT retried (not transient)."""
        executor = CommandExecutor()
        result = executor.execute(("bash", "-c", "exit 42"), CommandPhase.DISCOVERY)
        assert not result.succeeded
        assert result.exit_code == 42
        assert result.retries_attempted == 0  # not retried — not transient
        assert result.diagnostics is not None
        assert "exited with code 42" in (result.diagnostics or "")

    def test_mutation_non_zero_exit_no_retry_without_safety(self) -> None:
        """Mutation with non-zero exit should NOT retry without safety check."""
        executor = CommandExecutor()
        result = executor.execute(("bash", "-c", "exit 7"), CommandPhase.LIFECYCLE_MUTATION)
        assert not result.succeeded
        assert result.exit_code == 7
        assert result.retries_attempted == 0


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_discovery_timeout_is_retried(self) -> None:
        """Discovery timeout is transient — should be retried."""
        executor = CommandExecutor(discovery_timeout=0.5, discovery_retries=2)
        result = executor.execute(("sleep", "10"), CommandPhase.DISCOVERY)
        assert not result.succeeded
        assert result.timed_out
        assert result.retries_attempted == 2  # 1 initial + 2 retries
        assert result.diagnostics is not None

    def test_mutation_timeout_no_retry_without_safety(self) -> None:
        """Mutation timeout — no retry without safety check."""
        executor = CommandExecutor(mutation_timeout=0.5, mutation_retries=1)
        result = executor.execute(("sleep", "10"), CommandPhase.LIFECYCLE_MUTATION)
        assert not result.succeeded
        assert result.timed_out
        assert result.retries_attempted == 0  # no safety check → no retry

    def test_mutation_timeout_with_safety_retried(self) -> None:
        """Mutation timeout IS retried when safety check passes."""
        executor = CommandExecutor(mutation_timeout=0.5, mutation_retries=1)
        result = executor.execute(
            ("sleep", "10"),
            CommandPhase.LIFECYCLE_MUTATION,
            retry_safety_check=lambda r: True,  # always safe
        )
        assert not result.succeeded
        assert result.timed_out
        assert result.retries_attempted == 1  # 1 retry because safety check passed

    def test_custom_timeout_overrides_default(self) -> None:
        executor = CommandExecutor(discovery_timeout=30)
        result = executor.execute(("sleep", "10"), CommandPhase.DISCOVERY, timeout=0.3)
        assert result.timed_out
        # Should timeout at ~0.3s, not 30s


# ---------------------------------------------------------------------------
# Retryable transient failure (network-like patterns)
# ---------------------------------------------------------------------------

class TestTransientFailureRetry:
    def test_discovery_network_error_is_retried(self) -> None:
        """A stderr message matching a transient pattern triggers retries."""
        executor = CommandExecutor(discovery_retries=2)
        # Use bash to write a transient-looking message to stderr and exit non-zero
        result = executor.execute(
            ("bash", "-c", 'echo "fatal: unable to access" >&2; exit 1'),
            CommandPhase.DISCOVERY,
        )
        assert not result.succeeded
        assert result.retries_attempted == 2  # retried because it looks transient
        assert "unable to access" in result.stderr.lower()

    def test_discovery_connection_reset_is_retried(self) -> None:
        executor = CommandExecutor(discovery_retries=2)
        result = executor.execute(
            ("bash", "-c", 'echo "Connection reset by peer" >&2; exit 1'),
            CommandPhase.DISCOVERY,
        )
        assert result.retries_attempted == 2


# ---------------------------------------------------------------------------
# Non-retryable failure
# ---------------------------------------------------------------------------

class TestNonRetryableFailure:
    def test_discovery_non_transient_not_retried(self) -> None:
        executor = CommandExecutor(discovery_retries=2)
        result = executor.execute(
            ("bash", "-c", 'echo "something went wrong" >&2; exit 1'),
            CommandPhase.DISCOVERY,
        )
        assert result.retries_attempted == 0  # no transient pattern match

    def test_mutation_non_transient_no_retry(self) -> None:
        executor = CommandExecutor(mutation_retries=1)
        result = executor.execute(
            ("bash", "-c", "exit 99"),
            CommandPhase.LIFECYCLE_MUTATION,
            retry_safety_check=lambda r: False,
        )
        assert result.retries_attempted == 0
        assert result.exit_code == 99  # would be -1 or 99 depending on timing

    def test_mutation_safety_check_blocks_retry(self) -> None:
        """Even on a transient-looking failure, safety check can block retry."""
        executor = CommandExecutor(mutation_retries=1)
        result = executor.execute(
            ("bash", "-c", 'echo "fatal: unable to access" >&2; exit 1'),
            CommandPhase.LIFECYCLE_MUTATION,
            retry_safety_check=lambda r: False,
        )
        assert result.retries_attempted == 0  # safety check blocked it


# ---------------------------------------------------------------------------
# Phase-specific retry decisions
# ---------------------------------------------------------------------------

class TestPhaseSpecificRetry:
    def test_discovery_uses_short_timeout(self) -> None:
        executor = CommandExecutor(discovery_timeout=30.0, mutation_timeout=120.0)
        # Fast command — just verify defaults are set correctly
        result = executor.execute(("echo", "x"), CommandPhase.DISCOVERY)
        assert result.succeeded
        assert result.phase == CommandPhase.DISCOVERY

    def test_mutation_uses_long_timeout(self) -> None:
        executor = CommandExecutor(discovery_timeout=30.0, mutation_timeout=120.0)
        result = executor.execute(("echo", "x"), CommandPhase.LIFECYCLE_MUTATION)
        assert result.succeeded
        assert result.phase == CommandPhase.LIFECYCLE_MUTATION

    def test_discovery_succeeds_after_retries(self) -> None:
        """Discovery retries transient failures until success."""
        counter = {"calls": 0}

        class FakePopen:
            """Simulates a transient failure on first call, success on second."""
            def __init__(self, args, **kwargs):
                counter["calls"] += 1
                self.args = args
                self._call_num = counter["calls"]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

            def communicate(self, input=None, timeout=None):
                return ("", "")

            @property
            def returncode(self):
                if self._call_num == 1:
                    return 1  # first call fails
                return 0  # second call succeeds

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                pass

        import rangkai.command_executor as mod
        original_popen = subprocess.Popen
        try:
            subprocess.Popen = FakePopen
            # Patch _is_transient_failure to treat exit_code==1 as transient
            original_is_transient = mod._is_transient_failure
            mod._is_transient_failure = lambda r: r.exit_code == 1

            executor = CommandExecutor(discovery_retries=1)
            result = executor.execute_discovery(
                ("gh", "issue", "list"),
            )
            assert result.succeeded
            assert counter["calls"] == 2
            assert result.retries_attempted == 1
        finally:
            subprocess.Popen = original_popen
            mod._is_transient_failure = original_is_transient


# ---------------------------------------------------------------------------
# Jittered backoff
# ---------------------------------------------------------------------------

class TestJitteredBackoff:
    def test_retries_have_delay(self) -> None:
        """Verify that retries introduce a measurable delay."""
        import random
        # Force deterministic jitter for the test
        original_uniform = random.uniform
        try:
            random.uniform = lambda a, b: 0.01  # tiny delay
            executor = CommandExecutor(discovery_timeout=0.5, discovery_retries=1)
            counter = {"calls": 0}

            class CountingPopen:
                def __init__(self, args, **kwargs):
                    counter["calls"] += 1
                    self.args = args

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    pass

                @property
                def returncode(self):
                    return 1

                def communicate(self, input=None, timeout=None):
                    return ("Connection refused", "")

                def poll(self):
                    return self.returncode

                def wait(self, timeout=None):
                    return self.returncode

                def kill(self):
                    pass

            import rangkai.command_executor as mod
            original_popen = subprocess.Popen
            original_is_transient = mod._is_transient_failure
            try:
                subprocess.Popen = CountingPopen
                mod._is_transient_failure = lambda r: True
                start = time.monotonic()
                result = executor.execute_discovery(("gh", "view", "1"))
                elapsed = time.monotonic() - start
                assert counter["calls"] == 2  # 1 initial + 1 retry
                assert elapsed >= 0.005  # at least some delay
            finally:
                subprocess.Popen = original_popen
                mod._is_transient_failure = original_is_transient
        finally:
            random.uniform = original_uniform


# ---------------------------------------------------------------------------
# CommandError
# ---------------------------------------------------------------------------

class TestCommandError:
    def test_command_error_includes_diagnostics(self) -> None:
        result = _result(
            command=("git", "push"),
            phase=CommandPhase.LIFECYCLE_MUTATION,
            exit_code=1,
            stderr="Permission denied",
            diagnostics="Command exited with code 1; stderr: Permission denied",
        )
        exc = CommandError(result)
        assert "Command failed" in str(exc)
        assert "exit_code=1" in str(exc)
        assert "Permission denied" in str(exc)

    def test_command_error_timed_out(self) -> None:
        result = _result(timed_out=True, diagnostics="Command timed out after 30s")
        exc = CommandError(result)
        assert "timed out" in str(exc)


# ---------------------------------------------------------------------------
# Transient failure detection
# ---------------------------------------------------------------------------

class TestIsTransientFailure:
    def test_timed_out_is_transient(self) -> None:
        r = _result(timed_out=True)
        assert _is_transient_failure(r) is True

    def test_network_patterns_are_transient(self) -> None:
        for pattern in [
            "Could not resolve host",
            "Failed to connect to",
            "Connection refused",
            "Connection reset",
            "Temporary failure in name resolution",
        ]:
            r = _result(stderr=pattern)
            assert _is_transient_failure(r) is True, f"'{pattern}' should be transient"

    def test_non_network_exit_is_not_transient(self) -> None:
        r = _result(stderr="fatal: Not a git repository")
        assert _is_transient_failure(r) is False

    def test_empty_stderr_not_transient(self) -> None:
        r = _result(stderr="", exit_code=1)
        assert _is_transient_failure(r) is False


# ---------------------------------------------------------------------------
# Subprocess error (OSError)
# ---------------------------------------------------------------------------

class TestSubprocessError:
    def test_file_not_found(self) -> None:
        executor = CommandExecutor()
        result = executor.execute(
            ("/nonexistent/command",),
            CommandPhase.DISCOVERY,
        )
        assert not result.succeeded
        assert result.exit_code == -1
        assert result.retries_attempted == 0  # not transient
