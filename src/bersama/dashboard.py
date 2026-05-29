from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from bersama.config import AppConfig, ConfigError, RepoConfig
from bersama.github_issues import GitHubIssueGateway
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from bersama.reconciliation import ReconciliationService

ReconciliationServiceFactory = Callable[[RepoConfig], ReconciliationService]
PrdPreparationServiceFactory = Callable[[RepoConfig], PrdPreparationService]


def create_dashboard_app(
    *,
    config: AppConfig,
    reconciliation_service_factory: ReconciliationServiceFactory | None = None,
    prd_preparation_service_factory: PrdPreparationServiceFactory | None = None,
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

    service_factory = reconciliation_service_factory or build_service
    prd_service_factory = (
        prd_preparation_service_factory or build_prd_preparation_service
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

    return app
