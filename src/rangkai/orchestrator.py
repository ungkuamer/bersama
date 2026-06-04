from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, Executor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END

from rangkai.config import AppConfig, QualityGateConfig
from rangkai.github_issues import GitHubIssueGateway
from rangkai.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from rangkai.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from rangkai.execution import HarnessExecutionService
from rangkai.integration import IntegrationWorkspaceGateway, IntegrationService
from rangkai.reconciliation import ReconciliationService
from rangkai.repo_lock import RepoLock


@dataclass(frozen=True)
class SchedulerEvent:
    event: str  # e.g. "claim.attempt", "claim.succeeded", "agent_run.start"
    issue_number: int
    agent_run_id: str | None = None
    status: str | None = None  # "succeeded", "failed", etc.
    detail: str | None = None


_VALIDATION_STATUSES = frozenset({"passed", "failed", "error"})


def _parse_validation_result(stdout: str) -> dict | None:
    """Parse a Saringan-style Validation Result JSON from command stdout.

    Looks for a JSON object containing a ``status`` key with a recognised
    value (passed, failed, error).  Returns the parsed dict or None.
    """
    if not stdout.strip():
        return None

    import re
    # Try to extract the first JSON object from stdout
    # Look for { ... } pattern
    brace_depth = 0
    start = -1
    for i, ch in enumerate(stdout):
        if ch == "{":
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start >= 0:
                candidate = stdout[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "status" in parsed:
                        status_val = str(parsed["status"]).lower()
                        if status_val in _VALIDATION_STATUSES:
                            return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
                # Reset and continue looking
                start = -1

    return None


def _build_gate_blocked_comment(
    *,
    failure_reason: str,
    gate_status: str,
    exit_code: int,
    timed_out: bool,
    parsed_result: dict | None,
    stdout: str,
    stderr: str,
    implementation_branch: str,
    prd_branch: str,
    worktree_path: str,
) -> str:
    """Build a diagnostic comment for a blocked quality gate."""
    lines = [
        f"Quality Gate blocked Integration Pull Request creation for implementation branch `{implementation_branch}`",
        f" into PRD branch `{prd_branch}`.",
        "",
        f"**Gate Status:** {gate_status}",
        f"**Exit Code:** {exit_code}",
    ]
    if timed_out:
        lines.append("**Timed Out:** yes")
    if failure_reason:
        lines.append(f"**Reason:** {failure_reason}")

    if parsed_result is not None:
        # Include failed checks if available
        checks = parsed_result.get("checks")
        if isinstance(checks, list) and checks:
            lines.append("")
            lines.append("**Failed Checks:**")
            for check in checks:
                if isinstance(check, dict):
                    name = check.get("name", "unknown")
                    status = check.get("status", "unknown")
                    lines.append(f"- `{name}`: {status}")
        # Include message if present
        message = parsed_result.get("message")
        if isinstance(message, str) and message:
            lines.append(f"**Message:** {message}")

    if stderr.strip():
        # Bound stderr to last 500 chars
        stderr_snippet = stderr.strip()[-500:]
        lines.append("")
        lines.append("**stderr (last 500 chars):**")
        lines.append("```")
        lines.append(stderr_snippet)
        lines.append("```")

    lines.append("")
    lines.append(f"**Diagnostics persisted at:** `{worktree_path}/quality-gate/`")
    lines.append("- `stdout.txt` — complete stdout output")
    lines.append("- `stderr.txt` — complete stderr output")
    if parsed_result is not None:
        lines.append("- `result.json` — parsed validation result")

    return "\n".join(lines)


@dataclass(frozen=True)
class RunPlan:
    repo_name: str
    repo_path: str
    main_branch: str
    worktree_root: str
    harness_name: str
    command: tuple[str, ...]


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def build_run_plan(config: AppConfig, repo_name: str) -> RunPlan:
    repo = config.repo(repo_name)
    harness = config.harness(repo.default_harness)

    format_context = {
        "repo_name": repo.name,
        "repo_path": str(repo.repo_path),
        "main_branch": repo.main_branch,
        "worktree_root": str(repo.worktree_root),
        "global_concurrency": str(repo.global_concurrency),
        "per_prd_concurrency": str(repo.per_prd_concurrency),
        "harness_name": harness.name,
    }

    rendered_args = tuple(
        part.format_map(SafeFormatDict(format_context)) for part in harness.args_template
    )
    command = (harness.command, *rendered_args)

    return RunPlan(
        repo_name=repo.name,
        repo_path=str(repo.repo_path),
        main_branch=repo.main_branch,
        worktree_root=str(repo.worktree_root),
        harness_name=harness.name,
        command=command,
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_event_emitter(event: SchedulerEvent) -> None:
    print(json.dumps({
        "event": event.event,
        "issue_number": event.issue_number,
        "agent_run_id": event.agent_run_id,
        "status": event.status,
        "detail": event.detail,
    }), file=sys.stdout, flush=True)


class OrchestrationState(TypedDict, total=False):
    repo_name: str
    config: AppConfig
    claimable_issues: List[int]


class Orchestrator:
    def __init__(
        self,
        *,
        issues_gateway: Optional[Any] = None,
        git_workspace_gateway: Optional[Any] = None,
        claim_workspace_gateway: Optional[Any] = None,
        integration_workspace_gateway: Optional[Any] = None,
        now_provider: Optional[callable] = None,
        executor: Optional[Executor] = None,
        event_emitter: Optional[callable] = None,
    ) -> None:
        self.issues = issues_gateway or GitHubIssueGateway()
        self.git_workspace = git_workspace_gateway or GitWorkspaceGateway()
        self.claim_workspace = claim_workspace_gateway or ClaimWorkspaceGateway()
        self.integration_workspace = integration_workspace_gateway or IntegrationWorkspaceGateway()
        self.now_provider = now_provider or _utc_now
        self._repo_lock: RepoLock | None = None  # bound when repo_path is known
        self._executor = executor if executor is not None else ThreadPoolExecutor()
        self._event_emitter = event_emitter or _default_event_emitter
        self._active_agent_run_issue_numbers: set[int] = set()

        # Track whether internal gateways were created so we can inject
        # the RepoLock later when repo_path is known (via _bind_repo_lock).
        self._internal_git_workspace = git_workspace_gateway is None
        self._internal_claim_workspace = claim_workspace_gateway is None
        self._internal_integration_workspace = integration_workspace_gateway is None

        self.prd_preparation_service = PrdPreparationService(
            issues=self.issues,
            workspace=self.git_workspace,
        )
        self.claim_service = ImplementationClaimService(
            issues=self.issues,
            workspace=self.claim_workspace,
            now_provider=self.now_provider,
        )
        self.execution_service = HarnessExecutionService(
            issues=self.issues,
        )
        self.integration_service = IntegrationService(
            issues=self.issues,
            workspace=self.integration_workspace,
        )
        self.reconciliation_service = ReconciliationService(
            issues=self.issues,
            now_provider=self.now_provider,
        )

    def _emit_scheduler_diagnostic(self, *, issue_number: int, detail: str) -> None:
        self._event_emitter(SchedulerEvent(
            event="scheduler.diagnostic",
            issue_number=issue_number,
            agent_run_id=None,
            status="recoverable",
            detail=detail,
        ))

    def _bind_repo_lock(self, repo_path: str) -> None:
        """Create a system-wide RepoLock bound to *repo_path* and inject it
        into the internally-created gateways so that all shared repository
        metadata mutations are serialized across processes.

        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._repo_lock is not None:
            return  # already bound
        self._repo_lock = RepoLock(repo_path=repo_path)
        if self._internal_git_workspace:
            self.git_workspace._lock = self._repo_lock
        if self._internal_claim_workspace:
            self.claim_workspace._lock = self._repo_lock
        if self._internal_integration_workspace:
            self.integration_workspace._lock = self._repo_lock

    def reconcile_start(self, state: OrchestrationState) -> OrchestrationState:
        self.reconciliation_service.reconcile()
        self._poll_pending_integrations(state)
        return state

    def prepare_prds(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        records = self.issues.list_issues(state="open", labels=("prd",))
        for record in records:
            from rangkai.issues import parse_issue, GitHubIssue, PrdIssue
            parsed = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )
            if isinstance(parsed, PrdIssue) and not parsed.orchestration.prd_branch:
                self.prd_preparation_service.prepare_issue(
                    repo_path=str(repo_config.repo_path),
                    main_branch=repo_config.main_branch,
                    issue_number=record.number,
                )
        return state

    def plan_actions(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])

        from datetime import UTC, datetime, timedelta
        now_str = self.now_provider()
        normalized = now_str.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        now_dt = datetime.fromisoformat(normalized)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=UTC)
        else:
            now_dt = now_dt.astimezone(UTC)

        # Fetch open issues without time window (must see all open
        # issues for correct scheduling).
        open_records = list(
            self.issues.list_issues(
                state="open",
                labels=("prd", "implementation"),
            )
        )
        # Fetch closed issues with a 24h sliding window to keep the
        # dataset manageable.
        updated_since = (now_dt - timedelta(hours=24)).strftime("%Y-%m-%d")
        closed_records = list(
            self.issues.list_issues(
                state="closed",
                labels=("prd", "implementation"),
                updated_since=updated_since,
            )
        )
        # Deduplicate by number (open and closed fetches may overlap).
        records_by_number: dict[int, GitHubIssueRecord] = {}
        for rec in open_records + closed_records:
            records_by_number[rec.number] = rec
        records = list(records_by_number.values())

        # Resolve blocking dependencies that fell out of the sliding
        # window cache via single-issue lookups (gh issue view <num>).
        from rangkai.issues import parse_issue, GitHubIssue, ImplementationIssue
        records_by_number = {r.number: r for r in records}
        missing_blockers_by_issue: dict[int, set[int]] = {}
        for record in records:
            parsed = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )
            if isinstance(parsed, ImplementationIssue):
                for blocker_number in parsed.blocked_by:
                    if blocker_number not in records_by_number:
                        missing_blockers_by_issue.setdefault(record.number, set()).add(blocker_number)

        for issue_number, blocker_numbers in sorted(missing_blockers_by_issue.items()):
            for blocker_number in sorted(blocker_numbers):
                try:
                    blocker_record = self.issues.view_issue(blocker_number)
                    records.append(blocker_record)
                except Exception as exc:
                    self._emit_scheduler_diagnostic(
                        issue_number=issue_number,
                        detail=f"Blocking dependency #{blocker_number} lookup failed: {exc}",
                    )
                    # If the blocker lookup fails (e.g. issue was deleted),
                    # the planner will generate a diagnostic for it.
                    pass

        from rangkai.planner import plan_issue_actions
        planner_result = plan_issue_actions(
            tuple(records),
            global_concurrency=repo_config.global_concurrency,
            per_prd_concurrency=repo_config.per_prd_concurrency,
            stale_claim_timeout=timedelta(hours=2),
            now=now_dt,
            active_agent_run_issue_numbers=frozenset(self._active_agent_run_issue_numbers),
        )
        state["claimable_issues"] = sorted(planner_result.claimable_issue_numbers)

        # Poll pending integration PRs asynchronously during scheduling.
        self._poll_pending_integrations(state)

        return state

    def _run_quality_gate(
        self,
        *,
        repo_name: str,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
        config: AppConfig,
    ) -> bool | None:
        """Run the quality gate if enabled for the repo.

        Returns:
            True if gate is disabled or passes, False if gate fails,
            None if gate is enabled but couldn't be executed.

        On failure or error, persists diagnostics to the worktree,
        adds ``needs-triage`` label and a diagnostic comment to the
        implementation issue, and emits a ``quality_gate.blocked`` event.
        """
        repo = config.repo(repo_name)
        quality_gate = repo.quality_gate

        if not quality_gate.enabled:
            return True

        # Fetch issue details for context rendering
        try:
            issue_record = self.issues.view_issue(issue_number)
        except Exception as exc:
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail=f"Failed to fetch issue for quality gate: {exc}",
            ))
            return None

        from rangkai.issues import parse_issue, GitHubIssue, ImplementationIssue, PrdIssue
        parsed_issue = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed_issue, ImplementationIssue):
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail="Issue is not an Implementation Issue.",
            ))
            return None

        parent_prd_number = parsed_issue.parent_prd_number
        if parent_prd_number is None:
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail="Implementation Issue is missing parent PRD reference.",
            ))
            return None

        try:
            parent_record = self.issues.view_issue(parent_prd_number)
        except Exception as exc:
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail=f"Failed to fetch parent PRD for quality gate: {exc}",
            ))
            return None

        parent_issue = parse_issue(
            GitHubIssue(
                number=parent_record.number,
                title=parent_record.title,
                body=parent_record.body,
                labels=parent_record.labels,
            )
        )
        if not isinstance(parent_issue, PrdIssue):
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail=f"Parent Issue #{parent_prd_number} is not a PRD Issue.",
            ))
            return None

        prd_branch = parent_issue.orchestration.prd_branch
        implementation_branch = parsed_issue.orchestration.implementation_branch

        worktree_path = str(Path(worktree_root) / f"issue-{issue_number}")

        # Render command args template
        format_context = {
            "repo_name": repo.name,
            "repo_path": str(repo.repo_path),
            "worktree_root": str(repo.worktree_root),
            "issue_number": str(issue_number),
            "parent_prd_number": str(parent_prd_number),
            "prd_branch": prd_branch or "",
            "implementation_branch": implementation_branch or "",
            "worktree_path": worktree_path,
        }
        rendered_args = [
            part.format(**format_context) for part in quality_gate.args_template
        ]
        command = [quality_gate.command] + rendered_args

        # Execute quality gate command
        self._event_emitter(SchedulerEvent(
            event="quality_gate.start",
            issue_number=issue_number,
            status="running",
        ))

        # Capture variables for diagnostics persistence
        stdout = ""
        stderr = ""
        exit_code = -1
        timed_out = False
        parsed_result = None
        failure_reason = ""
        gate_status = ""

        try:
            timeout = quality_gate.timeout_seconds if quality_gate.timeout_seconds is not None else 300
            env = dict(os.environ)
            completed = subprocess.run(
                command,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            timed_out = False

            # Parse validation result JSON from stdout
            parsed_result = _parse_validation_result(stdout)

            if exit_code != 0:
                failure_reason = f"Quality gate command exited with code {exit_code}."
                gate_status = "failed"
            elif parsed_result is None:
                failure_reason = "Quality gate stdout did not contain valid Validation Result JSON."
                gate_status = "failed"
            else:
                gate_status = parsed_result.get("status", "")
                if gate_status == "passed":
                    self._event_emitter(SchedulerEvent(
                        event="quality_gate.passed",
                        issue_number=issue_number,
                        status="passed",
                    ))
                    return True
                else:
                    failure_reason = f"Quality gate status: {gate_status}"

            # If we got here with a non-passed status, the gate blocks.
            self._event_emitter(SchedulerEvent(
                event="quality_gate.failed",
                issue_number=issue_number,
                status="failed",
                detail=failure_reason,
            ))
            self._handle_gate_blocked(
                issue_number=issue_number,
                worktree_path=worktree_path,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=timed_out,
                parsed_result=parsed_result,
                failure_reason=failure_reason,
                gate_status=gate_status,
                implementation_branch=implementation_branch or "",
                prd_branch=prd_branch or "",
            )
            return False

        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            timed_out = True
            failure_reason = f"Quality gate timed out after {timeout}s."
            gate_status = "failed"
            self._event_emitter(SchedulerEvent(
                event="quality_gate.failed",
                issue_number=issue_number,
                status="failed",
                detail=failure_reason,
            ))
            self._handle_gate_blocked(
                issue_number=issue_number,
                worktree_path=worktree_path,
                stdout=stdout,
                stderr=stderr,
                exit_code=-1,
                timed_out=timed_out,
                parsed_result=None,
                failure_reason=failure_reason,
                gate_status=gate_status,
                implementation_branch=implementation_branch or "",
                prd_branch=prd_branch or "",
            )
            return False

        except Exception as exc:
            failure_reason = f"Quality gate execution error: {exc}"
            self._event_emitter(SchedulerEvent(
                event="quality_gate.error",
                issue_number=issue_number,
                status="failed",
                detail=failure_reason,
            ))
            self._handle_gate_blocked(
                issue_number=issue_number,
                worktree_path=worktree_path,
                stdout=stdout,
                stderr=stderr,
                exit_code=-1,
                timed_out=False,
                parsed_result=None,
                failure_reason=failure_reason,
                gate_status="error",
                implementation_branch=implementation_branch or "",
                prd_branch=prd_branch or "",
            )
            return None

    def _handle_gate_blocked(
        self,
        *,
        issue_number: int,
        worktree_path: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool,
        parsed_result: dict | None,
        failure_reason: str,
        gate_status: str,
        implementation_branch: str,
        prd_branch: str,
    ) -> None:
        """Persist diagnostics, label, and comment when a quality gate blocks integration."""
        # Persist diagnostics to worktree
        try:
            self._persist_gate_diagnostics(
                worktree_path=worktree_path,
                stdout=stdout,
                stderr=stderr,
                parsed_result=parsed_result,
            )
        except Exception:
            pass  # Best-effort persistence

        # Build diagnostic comment
        comment = _build_gate_blocked_comment(
            failure_reason=failure_reason,
            gate_status=gate_status,
            exit_code=exit_code,
            timed_out=timed_out,
            parsed_result=parsed_result,
            stdout=stdout,
            stderr=stderr,
            implementation_branch=implementation_branch,
            prd_branch=prd_branch,
            worktree_path=worktree_path,
        )

        # Notify the implementation issue
        try:
            self.issues.add_labels(issue_number, "needs-triage")
        except Exception:
            pass
        try:
            self.issues.add_comment(issue_number, comment)
        except Exception:
            pass

        # Emit blocked event
        self._event_emitter(SchedulerEvent(
            event="quality_gate.blocked",
            issue_number=issue_number,
            status="blocked",
            detail=failure_reason,
        ))

    @staticmethod
    def _persist_gate_diagnostics(
        *,
        worktree_path: str,
        stdout: str,
        stderr: str,
        parsed_result: dict | None,
    ) -> None:
        """Write quality gate diagnostics to the worktree for later inspection."""
        diag_dir = Path(worktree_path) / "quality-gate"
        diag_dir.mkdir(parents=True, exist_ok=True)

        # Truncate stdout/stderr to a bounded size (100KB each)
        max_size = 100 * 1024
        (diag_dir / "stdout.txt").write_text(stdout[:max_size], encoding="utf-8")
        (diag_dir / "stderr.txt").write_text(stderr[:max_size], encoding="utf-8")

        if parsed_result is not None:
            (diag_dir / "result.json").write_text(
                json.dumps(parsed_result, indent=2), encoding="utf-8"
            )

    def _run_agent_run(
        self,
        *,
        repo_name: str,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
        config: AppConfig,
    ) -> None:
        """Claim + Execute only. Successful results enter the serialized integration lane."""
        agent_run_id = f"run-{uuid.uuid4().hex[:8]}"

        # ── Phase 1: Claim ──────────────────────────────────────────
        self._event_emitter(SchedulerEvent(
            event="claim.attempt",
            issue_number=issue_number,
            agent_run_id=agent_run_id,
        ))
        try:
            claim_result = self.claim_service.claim_issue(
                repo_path=repo_path,
                worktree_root=worktree_root,
                issue_number=issue_number,
                agent_run_id=agent_run_id,
            )
        except Exception as exc:
            self._event_emitter(SchedulerEvent(
                event="claim.failed",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
                status="failed",
                detail=str(exc),
            ))
            print(
                f"[scheduler] claim error for #{issue_number}: {exc}",
                file=sys.stderr,
            )
            return

        if not claim_result.succeeded:
            self._event_emitter(SchedulerEvent(
                event="claim.failed",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
                status="failed",
                detail=claim_result.failure_message,
            ))
            print(
                f"[scheduler] claim failed for #{issue_number}: {claim_result.failure_message}",
                file=sys.stderr,
            )
            return

        self._event_emitter(SchedulerEvent(
            event="claim.succeeded",
            issue_number=issue_number,
            agent_run_id=agent_run_id,
            status="succeeded",
        ))

        # ── Phase 2: Execute ────────────────────────────────────────
        self._event_emitter(SchedulerEvent(
            event="agent_run.start",
            issue_number=issue_number,
            agent_run_id=agent_run_id,
        ))
        try:
            exec_result = self.execution_service.execute_run(
                repo_name=repo_name,
                issue_number=issue_number,
                config=config,
            )
        except Exception as exc:
            self._event_emitter(SchedulerEvent(
                event="agent_run.finished",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
                status="failed",
                detail=str(exc),
            ))
            print(
                f"[scheduler] execution error for #{issue_number}: {exc}",
                file=sys.stderr,
            )
            return

        finish_status = exec_result.status
        finish_detail = exec_result.failure_reason if finish_status != "succeeded" else None
        self._event_emitter(SchedulerEvent(
            event="agent_run.finished",
            issue_number=issue_number,
            agent_run_id=agent_run_id,
            status=finish_status,
            detail=finish_detail,
        ))

        if exec_result.status != "succeeded":
            reason = exec_result.failure_reason or exec_result.status
            print(
                f"[scheduler] execution non-success for #{issue_number}: status={exec_result.status}, reason={reason}",
                file=sys.stderr,
            )
            return

        # ── Phase 2.5: Quality Gate ─────────────────────────────
        gate_result = self._run_quality_gate(
            repo_name=repo_name,
            repo_path=repo_path,
            worktree_root=worktree_root,
            issue_number=issue_number,
            config=config,
        )
        if gate_result is False:
            print(
                f"[scheduler] quality gate failed for #{issue_number}",
                file=sys.stderr,
            )
            return
        if gate_result is None:
            print(
                f"[scheduler] quality gate error for #{issue_number}",
                file=sys.stderr,
            )
            return

        # ── Phase 3: Create Integration PR (non-blocking) ────────────
        # PR creation is fast (update, push, create).  CI validation
        # runs asynchronously on the remote and is polled later in
        # plan_actions / reconcile.
        try:
            integ_result = self.integration_service.create_integration_pr(
                repo_path=repo_path,
                worktree_root=worktree_root,
                issue_number=issue_number,
            )
            self._event_emitter(SchedulerEvent(
                event="integration.pr_created",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
                status=integ_result.status,
                detail=integ_result.failure_message,
            ))
        except Exception as exc:
            self._event_emitter(SchedulerEvent(
                event="integration.pr_created",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
                status="failed",
                detail=str(exc),
            ))

    def execute_claims(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        claimable_issues = state.get("claimable_issues", [])

        if not claimable_issues:
            return state

        # Track in-memory active Agent Runs so the planner knows about them
        # during subsequent scheduling passes (e.g. in continuous mode).
        for issue_number in claimable_issues:
            self._active_agent_run_issue_numbers.add(issue_number)

        futures = []
        for issue_number in claimable_issues:
            future = self._executor.submit(
                self._run_agent_run,
                repo_name=state["repo_name"],
                repo_path=str(repo_config.repo_path),
                worktree_root=str(repo_config.worktree_root),
                issue_number=issue_number,
                config=state["config"],
            )
            futures.append(future)

        try:
            # Wait for all Agent Runs (claim + execute) to complete.
            # Integration runs in the background, serialized by the dedicated worker.
            for future in futures:
                future.result()
        finally:
            # Clear in-memory tracking now that all dispatched runs have finished
            # execution or an executor future has raised unexpectedly. Agent Run
            # Capacity is freed immediately — integration does not consume capacity.
            for issue_number in claimable_issues:
                self._active_agent_run_issue_numbers.discard(issue_number)

        return state

    def reconcile_end(self, state: OrchestrationState) -> OrchestrationState:
        self.reconciliation_service.reconcile()
        self._poll_pending_integrations(state)
        return state

    def _poll_pending_integrations(self, state: OrchestrationState) -> None:
        """Poll integration PRs whose status is ``pending_validation``.

        Called from ``plan_actions`` and ``reconcile`` so that CI/CD
        validation progresses asynchronously across scheduling cycles.
        """
        repo_config = state["config"].repo(state["repo_name"])
        repo_path = str(repo_config.repo_path)
        worktree_root = str(repo_config.worktree_root)

        # Fetch open implementation issues that may have pending integrations.
        # We only need open issues since closed ones have already been integrated.
        try:
            open_records = self.issues.list_issues(
                state="open",
                labels=("implementation",),
            )
        except Exception as exc:
            self._emit_scheduler_diagnostic(
                issue_number=0,
                detail=f"Integration Pull Request polling issue listing failed: {exc}",
            )
            return

        from rangkai.issues import parse_issue, GitHubIssue, ImplementationIssue

        for record in open_records:
            parsed = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )
            if not isinstance(parsed, ImplementationIssue):
                continue

            orchestration = parsed.orchestration
            if orchestration.integration_status != "pending_validation":
                continue
            if not orchestration.integration_pr or orchestration.integration_pr == "N/A":
                continue

            # Poll this integration PR
            try:
                result = self.integration_service.poll_integration_pr(
                    repo_path=repo_path,
                    worktree_root=worktree_root,
                    issue_number=record.number,
                )
                if result.status in ("succeeded", "failed"):
                    self._event_emitter(SchedulerEvent(
                        event="integration.poll_result",
                        issue_number=record.number,
                        agent_run_id=orchestration.agent_run_id,
                        status=result.status,
                        detail=result.failure_message,
                    ))
            except Exception as exc:
                self._event_emitter(SchedulerEvent(
                    event="integration.poll_failed",
                    issue_number=record.number,
                    agent_run_id=orchestration.agent_run_id,
                    status="failed",
                    detail=str(exc),
                ))

    def build_workflow(self) -> Any:
        workflow = StateGraph(OrchestrationState)
        workflow.add_node("reconcile_start", self.reconcile_start)
        workflow.add_node("prepare_prds", self.prepare_prds)
        workflow.add_node("plan_actions", self.plan_actions)
        workflow.add_node("execute_claims", self.execute_claims)
        workflow.add_node("reconcile_end", self.reconcile_end)

        workflow.set_entry_point("reconcile_start")
        workflow.add_edge("reconcile_start", "prepare_prds")
        workflow.add_edge("prepare_prds", "plan_actions")
        workflow.add_edge("plan_actions", "execute_claims")
        workflow.add_edge("execute_claims", "reconcile_end")
        workflow.add_edge("reconcile_end", END)

        return workflow.compile()

    def run(self, repo_name: str, config: AppConfig, continuous: bool = False) -> None:
        repo_config = config.repo(repo_name)
        self._bind_repo_lock(str(repo_config.repo_path))

        # Wire Discord notifier if configured
        if config.discord.enabled and config.discord.webhook_url:
            from rangkai.discord_notifier import DiscordNotifier
            notifier = DiscordNotifier(config.discord.webhook_url)
            self.execution_service.set_discord_notifier(notifier)
            self.reconciliation_service.set_discord_notifier(notifier)

        # Wire telemetry adapter if configured
        if config.observability.enabled:
            from rangkai.telemetry import TelemetryAdapter
            telemetry = TelemetryAdapter(config=config.observability)
            self.reconciliation_service.set_telemetry(telemetry)

        if continuous:
            self._run_continuous(repo_name, config)
        else:
            compiled_graph = self.build_workflow()
            initial_state: OrchestrationState = {
                "repo_name": repo_name,
                "config": config,
                "claimable_issues": [],
            }
            compiled_graph.invoke(initial_state)

    def _run_continuous(self, repo_name: str, config: AppConfig) -> None:
        """Continuous drain scheduling for dependency waves.

        Reconciliation runs at orchestrator start, after meaningful
        outcomes (integration drain), and at orchestrator end — without
        requiring a full reconciliation before every slot check.

        The loop drains integration completions *inside* the scheduling
        loop so newly-unblocked Ready Implementation Issues become
        claimable within the same orchestrator invocation.

        Stop condition: no claimable issues AND no active Agent Runs
        AND no pending integrations.
        """
        # Phase 0: Bind the system-wide repo lock to the repository directory.
        repo_config = config.repo(repo_name)
        self._bind_repo_lock(str(repo_config.repo_path))

        # Phase 1: Reconciliation at orchestrator start (once).
        self.reconciliation_service.reconcile()

        # Phase 2: PRD preparation (once — no need to re-prepare every pass).
        state: OrchestrationState = {
            "repo_name": repo_name,
            "config": config,
            "claimable_issues": [],
        }
        state = self.prepare_prds(state)

        # Phase 3: Continuous scheduling loop.
        while True:
            # ---- Planning Pass ----
            state = self.plan_actions(state)
            claimable = state.get("claimable_issues", [])

            # ---- Stop Condition ----
            # Stop only when truly idle: nothing claimable and no active
            # Agent Runs.
            active_runs = bool(self._active_agent_run_issue_numbers)
            if not claimable and not active_runs:
                break

            if claimable:
                # ---- Execute ----
                # Dispatches claimable issues, waits for their execution
                # to complete, and creates Integration PRs for successful runs.
                state = self.execute_claims(state)

            # ---- Meaningful-Outcome Reconciliation ----
            # After execution + PR creation, issue states may have changed
            # (issues closed, labels updated, etc.).  Also polls pending
            # integration PRs for CI completion.
            self.reconciliation_service.reconcile()
            self._poll_pending_integrations(state)

        # Phase 4: Final reconciliation at orchestrator end.
        self.reconciliation_service.reconcile()
        self._poll_pending_integrations(state)
