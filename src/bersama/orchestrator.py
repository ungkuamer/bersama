from __future__ import annotations

import queue
import threading
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
    ) -> None:
        self.issues = issues_gateway or GitHubIssueGateway()
        self.git_workspace = git_workspace_gateway or GitWorkspaceGateway()
        self.claim_workspace = claim_workspace_gateway or ClaimWorkspaceGateway()
        self.integration_workspace = integration_workspace_gateway or IntegrationWorkspaceGateway()
        self.now_provider = now_provider or _utc_now
        self._executor = executor if executor is not None else ThreadPoolExecutor()
        self._active_agent_run_issue_numbers: set[int] = set()

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

        # ── Serialized Integration Lane ───────────────────────────────
        # Successful Agent Runs enter this queue when execution completes.
        # A dedicated daemon thread drains the queue one item at a time,
        # serializing all PRD-branch mutations without consuming Agent Run
        # Capacity.
        self._integration_queue: queue.Queue[tuple[int, str, str]] = queue.Queue()
        self._integration_lock = threading.Lock()
        self._integration_worker_started = False

    def reconcile_start(self, state: OrchestrationState) -> OrchestrationState:
        self.reconciliation_service.reconcile()
        return state

    def prepare_prds(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        records = self.issues.list_issues(state="open")
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
        records = self.issues.list_issues(state="all")

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

        from bersama.planner import plan_issue_actions
        planner_result = plan_issue_actions(
            records,
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
            issue_number, repo_path, worktree_root = item
            try:
                with self._integration_lock:
                    self.integration_service.integrate_issue(
                        repo_path=repo_path,
                        worktree_root=worktree_root,
                        issue_number=issue_number,
                    )
            except Exception:
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
        import sys
        import uuid
        agent_run_id = f"run-{uuid.uuid4().hex[:8]}"

        # ── Phase 1: Claim ──────────────────────────────────────────
        try:
            claim_result = self.claim_service.claim_issue(
                repo_path=repo_path,
                worktree_root=worktree_root,
                issue_number=issue_number,
                agent_run_id=agent_run_id,
            )
        except Exception as exc:
            print(
                f"[scheduler] claim error for #{issue_number}: {exc}",
                file=sys.stderr,
            )
            return

        if not claim_result.succeeded:
            print(
                f"[scheduler] claim failed for #{issue_number}: {claim_result.failure_message}",
                file=sys.stderr,
            )
            return

        # ── Phase 2: Execute ────────────────────────────────────────
        try:
            exec_result = self.execution_service.execute_run(
                repo_name=repo_name,
                issue_number=issue_number,
                config=config,
            )
        except Exception as exc:
            print(
                f"[scheduler] execution error for #{issue_number}: {exc}",
                file=sys.stderr,
            )
            return

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
        self._integration_queue.put((issue_number, repo_path, worktree_root))

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
        compiled_graph = self.build_workflow()
        if continuous:
            while True:
                initial_state: OrchestrationState = {
                    "repo_name": repo_name,
                    "config": config,
                    "claimable_issues": [],
                }
                result_state = compiled_graph.invoke(initial_state)
                if result_state.get("claimable_issues"):
                    print("\n--- Continuous execution: claimable issues found. Looping to next planning pass... ---\n")
                    continue
                else:
                    break
        else:
            initial_state: OrchestrationState = {
                "repo_name": repo_name,
                "config": config,
                "claimable_issues": [],
            }
            compiled_graph.invoke(initial_state)

        # Wait for all pending integrations to complete before returning.
        # In continuous mode this ensures clean shutdown; in single-pass mode
        # it ensures the caller sees all integrations applied.
        self._drain_integration_queue()

