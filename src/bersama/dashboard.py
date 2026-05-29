from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from bersama.config import AppConfig, ConfigError, RepoConfig
from bersama.github_issues import GitHubIssueGateway
from bersama.reconciliation import ReconciliationService

ReconciliationServiceFactory = Callable[[RepoConfig], ReconciliationService]


def create_dashboard_app(
    *,
    config: AppConfig,
    reconciliation_service_factory: ReconciliationServiceFactory | None = None,
) -> FastAPI:
    app = FastAPI()

    def build_service(repo: RepoConfig) -> ReconciliationService:
        del repo
        return ReconciliationService(issues=GitHubIssueGateway())

    service_factory = reconciliation_service_factory or build_service

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

    return app
