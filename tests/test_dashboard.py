from pathlib import Path

from fastapi.testclient import TestClient

from bersama.claiming import ClaimResult
from bersama.config import AppConfig, HarnessConfig, RepoConfig
from bersama.dashboard import create_dashboard_app
from bersama.prd_preparation import PrdPreparationResult


class FakeReconciliationService:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile(self) -> None:
        self.calls += 1


class FakePrdPreparationService:
    def __init__(self, result: PrdPreparationResult) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self._result = result

    def prepare_issue(
        self, *, repo_path: str, main_branch: str, issue_number: int
    ) -> PrdPreparationResult:
        self.calls.append((repo_path, main_branch, issue_number))
        return self._result


class FakeImplementationClaimService:
    def __init__(self, result: ClaimResult) -> None:
        self.calls: list[tuple[str, str, int, str]] = []
        self._result = result

    def claim_issue(
        self,
        *,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
        agent_run_id: str,
    ) -> ClaimResult:
        self.calls.append((repo_path, worktree_root, issue_number, agent_run_id))
        return self._result


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


def test_prepare_prd_endpoint_returns_branch_metadata_on_success() -> None:
    service = FakePrdPreparationService(
        PrdPreparationResult(
            issue_number=15,
            prd_branch="prd/15-add-interactive-dashboard-backend-control-apis",
            reused_existing_branch=False,
            updated_issue_body=True,
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        prd_preparation_service_factory=lambda repo: service,
    )

    response = TestClient(app).post("/dashboard/repos/demo/prd-issues/15/prepare")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "repo": "demo",
        "action": "prepare-prd",
        "issue_number": 15,
        "prd_branch": "prd/15-add-interactive-dashboard-backend-control-apis",
        "reused_existing_branch": False,
        "updated_issue_body": True,
    }
    assert service.calls == [("/repos/demo", "main", 15)]


def test_prepare_prd_endpoint_returns_bad_request_for_known_failure() -> None:
    service = FakePrdPreparationService(
        PrdPreparationResult(
            issue_number=15,
            prd_branch=None,
            reused_existing_branch=False,
            updated_issue_body=False,
            failure_message="Issue is not a PRD Issue.",
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        prd_preparation_service_factory=lambda repo: service,
    )

    response = TestClient(app).post("/dashboard/repos/demo/prd-issues/15/prepare")

    assert response.status_code == 400
    assert response.json() == {"detail": "Issue is not a PRD Issue."}


def test_prepare_prd_endpoint_returns_server_error_for_unexpected_failure() -> None:
    class FailingPrdPreparationService:
        def prepare_issue(
            self, *, repo_path: str, main_branch: str, issue_number: int
        ) -> PrdPreparationResult:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=build_config(),
        prd_preparation_service_factory=lambda repo: FailingPrdPreparationService(),
    )

    response = TestClient(app).post("/dashboard/repos/demo/prd-issues/15/prepare")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "PRD preparation failed for repo 'demo': GitHub issue access failed"
    }


def test_claim_implementation_issue_endpoint_returns_claim_metadata_on_success() -> None:
    service = FakeImplementationClaimService(
        ClaimResult(
            issue_number=18,
            agent_run_id="run-123",
            implementation_branch="impl/15/18-add-implementation-issue-claim-dashboard-control",
            worktree_path="/worktrees/demo/issue-18",
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        implementation_claim_service_factory=lambda repo: service,
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/claim",
        json={"agent_run_id": "run-123"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "repo": "demo",
        "action": "claim-implementation-issue",
        "issue_number": 18,
        "agent_run_id": "run-123",
        "implementation_branch": "impl/15/18-add-implementation-issue-claim-dashboard-control",
        "worktree_path": "/worktrees/demo/issue-18",
    }
    assert service.calls == [
        ("/repos/demo", "/worktrees/demo", 18, "run-123")
    ]


def test_claim_implementation_issue_endpoint_requires_agent_run_id() -> None:
    app = create_dashboard_app(config=build_config())

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/claim",
        json={},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "agent_run_id"]
    assert response.json()["detail"][0]["type"] == "missing"


def test_claim_implementation_issue_endpoint_returns_bad_request_for_known_claim_failure() -> None:
    service = FakeImplementationClaimService(
        ClaimResult(
            issue_number=18,
            agent_run_id="run-123",
            implementation_branch=None,
            worktree_path=None,
            failure_message="Implementation Issue is already claimed.",
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        implementation_claim_service_factory=lambda repo: service,
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/claim",
        json={"agent_run_id": "run-123"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Implementation Issue is already claimed."
    }


def test_claim_implementation_issue_endpoint_returns_not_found_for_unknown_repo() -> None:
    app = create_dashboard_app(config=build_config())

    response = TestClient(app).post(
        "/dashboard/repos/missing/implementation-issues/18/claim",
        json={"agent_run_id": "run-123"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Unknown repo 'missing'. Available repos: demo."
    }


def test_claim_implementation_issue_endpoint_returns_server_error_for_unexpected_failure() -> None:
    class FailingImplementationClaimService:
        def claim_issue(
            self,
            *,
            repo_path: str,
            worktree_root: str,
            issue_number: int,
            agent_run_id: str,
        ) -> ClaimResult:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=build_config(),
        implementation_claim_service_factory=lambda repo: FailingImplementationClaimService(),
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/claim",
        json={"agent_run_id": "run-123"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Implementation issue claim failed for repo 'demo': GitHub issue access failed"
    }
