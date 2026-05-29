from pathlib import Path

from fastapi.testclient import TestClient

from bersama.config import AppConfig, HarnessConfig, RepoConfig
from bersama.dashboard import create_dashboard_app


class FakeReconciliationService:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile(self) -> None:
        self.calls += 1


def build_config() -> AppConfig:
    return AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=Path("/worktrees/demo"),
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
    )


def test_reconcile_endpoint_returns_success_response() -> None:
    service = FakeReconciliationService()
    app = create_dashboard_app(
        config=build_config(),
        reconciliation_service_factory=lambda repo: service,
    )

    response = TestClient(app).post("/dashboard/repos/demo/reconcile")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "repo": "demo",
        "action": "reconcile",
    }
    assert service.calls == 1


def test_reconcile_endpoint_returns_not_found_for_unknown_repo() -> None:
    app = create_dashboard_app(config=build_config())

    response = TestClient(app).post("/dashboard/repos/missing/reconcile")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Unknown repo 'missing'. Available repos: demo."
    }


def test_reconcile_endpoint_returns_server_error_for_reconciliation_failure() -> None:
    class FailingReconciliationService:
        def reconcile(self) -> None:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=build_config(),
        reconciliation_service_factory=lambda repo: FailingReconciliationService(),
    )

    response = TestClient(app).post("/dashboard/repos/demo/reconcile")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Reconciliation failed for repo 'demo': GitHub issue access failed"
    }
