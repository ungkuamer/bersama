from __future__ import annotations

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
    ) -> None:
        self.issues = issues_gateway or GitHubIssueGateway()
        self.git_workspace = git_workspace_gateway or GitWorkspaceGateway()
        self.claim_workspace = claim_workspace_gateway or ClaimWorkspaceGateway()
        self.integration_workspace = integration_workspace_gateway or IntegrationWorkspaceGateway()
        self.now_provider = now_provider or _utc_now

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
        )
        state["claimable_issues"] = list(planner_result.claimable_issue_numbers)
        return state

    def execute_claims(self, state: OrchestrationState) -> OrchestrationState:
        repo_config = state["config"].repo(state["repo_name"])
        claimable_issues = state.get("claimable_issues", [])

        import uuid
        for issue_number in claimable_issues:
            agent_run_id = f"run-{uuid.uuid4().hex[:8]}"
            claim_result = self.claim_service.claim_issue(
                repo_path=str(repo_config.repo_path),
                worktree_root=str(repo_config.worktree_root),
                issue_number=issue_number,
                agent_run_id=agent_run_id,
            )
            if not claim_result.succeeded:
                continue

            exec_result = self.execution_service.execute_run(
                repo_name=state["repo_name"],
                issue_number=issue_number,
                config=state["config"],
            )
            if exec_result.status != "succeeded":
                continue

            self.integration_service.integrate_issue(
                repo_path=str(repo_config.repo_path),
                worktree_root=str(repo_config.worktree_root),
                issue_number=issue_number,
            )
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

