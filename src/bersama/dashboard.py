from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bersama.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from bersama.config import AppConfig, ConfigError, RepoConfig
from bersama.github_issues import GitHubIssueGateway
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from bersama.reconciliation import ReconciliationService

ReconciliationServiceFactory = Callable[[RepoConfig], ReconciliationService]
PrdPreparationServiceFactory = Callable[[RepoConfig], PrdPreparationService]
ImplementationClaimServiceFactory = Callable[[RepoConfig], ImplementationClaimService]


class ClaimImplementationIssueRequest(BaseModel):
    agent_run_id: str


def create_dashboard_app(
    *,
    config: AppConfig,
    reconciliation_service_factory: ReconciliationServiceFactory | None = None,
    prd_preparation_service_factory: PrdPreparationServiceFactory | None = None,
    implementation_claim_service_factory: ImplementationClaimServiceFactory | None = None,
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

    service_factory = reconciliation_service_factory or build_service
    prd_service_factory = (
        prd_preparation_service_factory or build_prd_preparation_service
    )
    claim_service_factory = (
        implementation_claim_service_factory or build_implementation_claim_service
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
            "issue_number": result.issue_number,
            "agent_run_id": result.agent_run_id,
            "implementation_branch": result.implementation_branch,
            "worktree_path": result.worktree_path,
        }

    return app
