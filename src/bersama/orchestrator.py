from __future__ import annotations

import json
import queue
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Executor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END

from bersama.config import AppConfig
from bersama.github_issues import GitHubIssueGateway
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from bersama.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from bersama.execution import HarnessExecutionService
from bersama.integration import IntegrationWorkspaceGateway, IntegrationService
from bersama.reconciliation import ReconciliationService
from bersama.repo_lock import RepoLock


@dataclass(frozen=True)
class SchedulerEvent:
    event: str  # e.g. "claim.attempt", "claim.succeeded", "agent_run.start"
    issue_number: int
    agent_run_id: str | None = None
    status: str | None = None  # "succeeded", "failed", etc.
    detail: str | None = None


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

        # ── Serialized Integration Lane ───────────────────────────────
        # Successful Agent Runs enter this queue when execution completes.
        # A dedicated daemon thread drains the queue one item at a time,
        # serializing all PRD-branch mutations without consuming Agent Run
        # Capacity.
        self._integration_queue: queue.Queue[tuple[int, str, str, str]] = queue.Queue()
        self._integration_lock = threading.Lock()
        self._integration_worker_started = False

    def reconcile_start(self, state: OrchestrationState) -> OrchestrationState:
        self.reconciliation_service.reconcile()
        return state

    def prepare_prds(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        records = self.issues.list_issues(state="open", labels=("prd",))
        for record in records:
            from bersama.issues import parse_issue, GitHubIssue, PrdIssue
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
        from bersama.issues import parse_issue, GitHubIssue, ImplementationIssue
        records_by_number = {r.number: r for r in records}
        missing_blockers: set[int] = set()
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
                        missing_blockers.add(blocker_number)

        for blocker_number in sorted(missing_blockers):
            try:
                blocker_record = self.issues.view_issue(blocker_number)
                records.append(blocker_record)
            except Exception:
                # If the blocker lookup fails (e.g. issue was deleted),
                # the planner will generate a diagnostic for it.
                pass

        from bersama.planner import plan_issue_actions
        planner_result = plan_issue_actions(
            tuple(records),
            global_concurrency=repo_config.global_concurrency,
            per_prd_concurrency=repo_config.per_prd_concurrency,
            stale_claim_timeout=timedelta(hours=2),
            now=now_dt,
            active_agent_run_issue_numbers=frozenset(self._active_agent_run_issue_numbers),
        )
        state["claimable_issues"] = list(planner_result.claimable_issue_numbers)
        return state

    def _ensure_integration_worker(self) -> None:
        """Start the serialized integration worker thread if not already running."""
        if not self._integration_worker_started:
            self._integration_worker_started = True
            worker = threading.Thread(target=self._run_integration_worker, daemon=True)
            worker.start()

    def _run_integration_worker(self) -> None:
        """Continuously drain the integration queue, one issue at a time.
        The lock ensures only one integration mutates any PRD branch at a time."""
        while True:
            item = self._integration_queue.get()
            if item is None:  # sentinel
                break
            issue_number, agent_run_id, repo_path, worktree_root = item
            self._event_emitter(SchedulerEvent(
                event="integration.start",
                issue_number=issue_number,
                agent_run_id=agent_run_id,
            ))
            try:
                with self._integration_lock:
                    result = self.integration_service.integrate_issue(
                        repo_path=repo_path,
                        worktree_root=worktree_root,
                        issue_number=issue_number,
                    )
                self._event_emitter(SchedulerEvent(
                    event="integration.finished",
                    issue_number=issue_number,
                    agent_run_id=agent_run_id,
                    status=result.status,
                    detail=result.failure_message,
                ))
            except Exception as exc:
                self._event_emitter(SchedulerEvent(
                    event="integration.finished",
                    issue_number=issue_number,
                    agent_run_id=agent_run_id,
                    status="failed",
                    detail=str(exc),
                ))
                # Integrate_issue handles its own error reporting (labels, comments).
                pass
            finally:
                self._integration_queue.task_done()

    def _drain_integration_queue(self) -> None:
        """Wait for all pending integrations to complete. Called before shutdown."""
        self._integration_queue.join()

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

        # ── Phase 3: Enter Integration Lane ─────────────────────────
        # Do NOT block Agent Run Capacity here — integration is
        # serialized by a dedicated worker thread.
        self._integration_queue.put((issue_number, agent_run_id, repo_path, worktree_root))

    def execute_claims(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        claimable_issues = state.get("claimable_issues", [])

        if not claimable_issues:
            return state

        # Ensure the serialized integration worker is running.
        self._ensure_integration_worker()

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

        # Wait for all Agent Runs (claim + execute) to complete.
        # Integration runs in the background, serialized by the dedicated worker.
        for future in futures:
            future.result()

        # Clear in-memory tracking now that all dispatched runs have finished
        # execution. Agent Run Capacity is freed immediately — integration
        # does not consume capacity.
        for issue_number in claimable_issues:
            self._active_agent_run_issue_numbers.discard(issue_number)

        return state

    def reconcile_end(self, state: OrchestrationState) -> OrchestrationState:
        self.reconciliation_service.reconcile()
        return state

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
            # Wait for all pending integrations to complete before returning.
            self._drain_integration_queue()

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

        # Phase 3: Ensure the serialised integration worker is running.
        self._ensure_integration_worker()

        # Phase 4: Continuous scheduling loop.
        while True:
            # ---- Planning Pass ----
            state = self.plan_actions(state)
            claimable = state.get("claimable_issues", [])

            # ---- Stop Condition ----
            # Stop only when truly idle: nothing claimable, no active
            # Agent Runs, and no integrations still in flight.
            active_runs = bool(self._active_agent_run_issue_numbers)
            pending_integrations = self._integration_queue.unfinished_tasks > 0
            if not claimable and not active_runs and not pending_integrations:
                break

            if claimable:
                # ---- Execute ----
                # Dispatches claimable issues, waits for their execution
                # to complete, and enqueues successful runs for integration.
                state = self.execute_claims(state)

            # ---- Drain Integrations ----
            # Wait for all pending integrations to finish *before* the
            # next planning pass.  This is the key to dependency-wave
            # draining: integrated (closed) issues unblock dependents.
            self._drain_integration_queue()

            # ---- Meaningful-Outcome Reconciliation ----
            # After integrations, issue states may have changed
            # (issues closed, labels updated, etc.).
            self.reconciliation_service.reconcile()

        # Phase 5: Final reconciliation at orchestrator end.
        self.reconciliation_service.reconcile()

        # Drain any straggling integrations (should be none, but defensive).
        self._drain_integration_queue()

