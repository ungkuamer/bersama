from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from bersama.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from bersama.config import AppConfig, ConfigError, RepoConfig
from bersama.execution import HarnessExecutionService
from bersama.github_issues import GitHubIssueGateway
from bersama.integration import IntegrationService, IntegrationWorkspaceGateway
from bersama.issues import GitHubIssue, ImplementationIssue, parse_issue
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from bersama.reconciliation import ReconciliationService

ReconciliationServiceFactory = Callable[[RepoConfig], ReconciliationService]
PrdPreparationServiceFactory = Callable[[RepoConfig], PrdPreparationService]
ImplementationClaimServiceFactory = Callable[[RepoConfig], ImplementationClaimService]
ExecutionServiceFactory = Callable[[RepoConfig], HarnessExecutionService]
IntegrationServiceFactory = Callable[[RepoConfig], IntegrationService]
IssueGatewayFactory = Callable[[], GitHubIssueGateway]
BackgroundTaskScheduler = Callable[..., object]


class ClaimImplementationIssueRequest(BaseModel):
    agent_run_id: str


def create_dashboard_app(
    *,
    config: AppConfig,
    reconciliation_service_factory: ReconciliationServiceFactory | None = None,
    prd_preparation_service_factory: PrdPreparationServiceFactory | None = None,
    implementation_claim_service_factory: ImplementationClaimServiceFactory | None = None,
    execution_service_factory: ExecutionServiceFactory | None = None,
    integration_service_factory: IntegrationServiceFactory | None = None,
    issue_gateway_factory: IssueGatewayFactory | None = None,
    background_task_scheduler: BackgroundTaskScheduler | None = None,
) -> FastAPI:
    app = FastAPI()

    def build_service(repo: RepoConfig) -> ReconciliationService:
        del repo
        return ReconciliationService(issues=GitHubIssueGateway())

    def build_prd_preparation_service(repo: RepoConfig) -> PrdPreparationService:
        del repo
        return PrdPreparationService(
            issues=GitHubIssueGateway(),
            workspace=GitWorkspaceGateway(),
        )

    def build_implementation_claim_service(repo: RepoConfig) -> ImplementationClaimService:
        del repo
        return ImplementationClaimService(
            issues=GitHubIssueGateway(),
            workspace=ClaimWorkspaceGateway(),
        )

    def build_execution_service(repo: RepoConfig) -> HarnessExecutionService:
        del repo
        return HarnessExecutionService(issues=GitHubIssueGateway())

    def build_integration_service(repo: RepoConfig) -> IntegrationService:
        del repo
        return IntegrationService(
            issues=GitHubIssueGateway(),
            workspace=IntegrationWorkspaceGateway(),
        )

    service_factory = reconciliation_service_factory or build_service
    prd_service_factory = (
        prd_preparation_service_factory or build_prd_preparation_service
    )
    claim_service_factory = (
        implementation_claim_service_factory or build_implementation_claim_service
    )
    execute_service_factory = execution_service_factory or build_execution_service
    integrate_service_factory = integration_service_factory or build_integration_service
    issues_factory = issue_gateway_factory or GitHubIssueGateway

    def schedule_background_task(
        background_tasks: BackgroundTasks,
        task: Callable[..., object],
        *args: object,
    ) -> None:
        if background_task_scheduler is not None:
            background_task_scheduler(task, *args)
            return
        background_tasks.add_task(task, *args)

    def run_issue_execution_in_background(repo_name: str, issue_number: int) -> None:
        repo = config.repo(repo_name)
        execution_result = execute_service_factory(repo).execute_run(
            repo_name=repo_name,
            issue_number=issue_number,
            config=config,
        )
        if execution_result.status == "succeeded":
            service_factory(repo).reconcile()

    def validate_claimed_issue_start(
        repo: RepoConfig, issue_number: int
    ) -> tuple[str, str, str]:
        issue_record = issues_factory().view_issue(issue_number)
        parsed_issue = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed_issue, ImplementationIssue):
            raise HTTPException(status_code=400, detail="Issue is not an Implementation Issue.")

        orchestration = parsed_issue.orchestration
        if not orchestration.agent_run_id or not orchestration.implementation_branch:
            raise HTTPException(status_code=400, detail="Implementation Issue is not claimed.")

        worktree_path = Path(repo.worktree_root) / f"issue-{issue_number}"
        if not worktree_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Implementation Issue worktree does not exist: {worktree_path}",
            )

        return (
            orchestration.agent_run_id,
            str(worktree_path / "run-state.json"),
            str(worktree_path / "harness.log"),
        )

    @app.post("/dashboard/repos/{repo_name}/reconcile")
    def reconcile_repo(repo_name: str) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            service_factory(repo).reconcile()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Reconciliation failed for repo '{repo.name}': {exc}",
            ) from exc

        return {
            "ok": True,
            "repo": repo.name,
            "action": "reconcile",
        }

    @app.post("/dashboard/repos/{repo_name}/prd-issues/{issue_number}/prepare")
    def prepare_prd_issue(repo_name: str, issue_number: int) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = prd_service_factory(repo).prepare_issue(
                repo_path=str(repo.repo_path),
                main_branch=repo.main_branch,
                issue_number=issue_number,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"PRD preparation failed for repo '{repo.name}': {exc}",
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "prepare-prd",
            "status": "prepared",
            "issue_number": result.issue_number,
            "prd_branch": result.prd_branch,
            "reused_existing_branch": result.reused_existing_branch,
            "updated_issue_body": result.updated_issue_body,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/claim")
    def claim_implementation_issue(
        repo_name: str,
        issue_number: int,
        request: ClaimImplementationIssueRequest,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = claim_service_factory(repo).claim_issue(
                repo_path=str(repo.repo_path),
                worktree_root=str(repo.worktree_root),
                issue_number=issue_number,
                agent_run_id=request.agent_run_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Implementation issue claim failed for repo '{repo.name}': {exc}",
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "claim-implementation-issue",
            "status": "claimed",
            "issue_number": result.issue_number,
            "agent_run_id": result.agent_run_id,
            "implementation_branch": result.implementation_branch,
            "worktree_path": result.worktree_path,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/start", status_code=202)
    def start_implementation_issue(
        repo_name: str,
        issue_number: int,
        background_tasks: BackgroundTasks,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            agent_run_id, run_state_path, log_path = validate_claimed_issue_start(
                repo, issue_number
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Implementation issue start failed for repo '{repo.name}': {exc}"
                ),
            ) from exc

        schedule_background_task(
            background_tasks,
            run_issue_execution_in_background,
            repo.name,
            issue_number,
        )

        return {
            "ok": True,
            "repo": repo.name,
            "action": "start-implementation-issue",
            "issue_number": issue_number,
            "agent_run_id": agent_run_id,
            "status": "started",
            "run_state_path": run_state_path,
            "log_path": log_path,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/integrate")
    def integrate_implementation_issue(
        repo_name: str,
        issue_number: int,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = integrate_service_factory(repo).integrate_issue(
                repo_path=str(repo.repo_path),
                worktree_root=str(repo.worktree_root),
                issue_number=issue_number,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Implementation issue integration failed for repo '{repo.name}': {exc}"
                ),
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "integrate-implementation-issue",
            "status": "integrated",
            "issue_number": result.issue_number,
            "implementation_branch": result.implementation_branch,
            "prd_branch": result.prd_branch,
        }

    return app
