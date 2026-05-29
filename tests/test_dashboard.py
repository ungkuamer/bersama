from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from bersama.claiming import ClaimResult
from bersama.config import AppConfig, HarnessConfig, RepoConfig
from bersama.dashboard import create_dashboard_app
from bersama.execution import ExecutionResult
from bersama.github_issues import GitHubIssueRecord
from bersama.integration import IntegrationResult
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


class FakeExecutionService:
    def __init__(self, result: ExecutionResult | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self._result = result or ExecutionResult(
            issue_number=18,
            status="succeeded",
            exit_code=0,
            new_commits=True,
            log_path="/worktrees/demo/issue-18/harness.log",
            run_state_path="/worktrees/demo/issue-18/run-state.json",
        )

    def execute_run(
        self, *, repo_name: str, issue_number: int, config: AppConfig
    ) -> ExecutionResult:
        del config
        self.calls.append((repo_name, issue_number))
        return self._result


class FakeIntegrationService:
    def __init__(self, result: IntegrationResult) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self._result = result

    def integrate_issue(
        self, *, repo_path: str, worktree_root: str, issue_number: int
    ) -> IntegrationResult:
        self.calls.append((repo_path, worktree_root, issue_number))
        return self._result


class FakeReconciliationRunner:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile(self) -> None:
        self.calls += 1


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self.issues[number]


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


def build_claimed_issue(*, body_suffix: str = "") -> GitHubIssueRecord:
    return GitHubIssueRecord(
        number=18,
        title="Implementation child",
        body=(
            "## Parent PRD\n"
            "#15\n\n"
            "## What to Build\n"
            "Build it.\n\n"
            "## Acceptance Criteria\n"
            "- [ ] Done.\n\n"
            "## Blocked By\n"
            "None\n\n"
            "## Orchestration\n"
            "- Agent Run: run-123\n"
            "- Claimed At: 2026-05-29T20:07:02Z\n"
            "- Implementation Branch: impl/15/18-implementation-child\n"
            f"{body_suffix}"
        ),
        labels=("implementation",),
        state="open",
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
        "status": "prepared",
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


def test_prepare_prd_endpoint_preserves_deliberate_not_found_errors() -> None:
    class MissingPrdPreparationService:
        def prepare_issue(
            self, *, repo_path: str, main_branch: str, issue_number: int
        ) -> PrdPreparationResult:
            raise HTTPException(status_code=404, detail="PRD Issue not found.")

    app = create_dashboard_app(
        config=build_config(),
        prd_preparation_service_factory=lambda repo: MissingPrdPreparationService(),
    )

    response = TestClient(app).post("/dashboard/repos/demo/prd-issues/15/prepare")

    assert response.status_code == 404
    assert response.json() == {"detail": "PRD Issue not found."}


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
        "status": "claimed",
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


def test_claim_implementation_issue_endpoint_preserves_deliberate_bad_request_errors() -> None:
    class InvalidClaimRequestService:
        def claim_issue(
            self,
            *,
            repo_path: str,
            worktree_root: str,
            issue_number: int,
            agent_run_id: str,
        ) -> ClaimResult:
            raise HTTPException(status_code=400, detail="Implementation Issue is not ready.")

    app = create_dashboard_app(
        config=build_config(),
        implementation_claim_service_factory=lambda repo: InvalidClaimRequestService(),
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/claim",
        json={"agent_run_id": "run-123"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Implementation Issue is not ready."}


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


def test_start_implementation_issue_endpoint_returns_accepted_and_schedules_background_run(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-18"
    issue_worktree.mkdir(parents=True)

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses=build_config().harnesses,
    )

    execution_service = FakeExecutionService()
    reconciliation_service = FakeReconciliationRunner()
    issue_gateway = FakeIssueGateway(build_claimed_issue())
    scheduled_jobs: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    app = create_dashboard_app(
        config=config,
        execution_service_factory=lambda repo: execution_service,
        reconciliation_service_factory=lambda repo: reconciliation_service,
        issue_gateway_factory=lambda: issue_gateway,
        background_task_scheduler=lambda task, *args, **kwargs: scheduled_jobs.append(
            (task, args, kwargs)
        ),
    )

    response = TestClient(app).post("/dashboard/repos/demo/implementation-issues/18/start")

    assert response.status_code == 202
    assert response.json() == {
        "ok": True,
        "repo": "demo",
        "action": "start-implementation-issue",
        "issue_number": 18,
        "agent_run_id": "run-123",
        "status": "started",
        "run_state_path": str(issue_worktree / "run-state.json"),
        "log_path": str(issue_worktree / "harness.log"),
    }
    assert execution_service.calls == []
    assert reconciliation_service.calls == 0
    assert len(scheduled_jobs) == 1

    task, args, kwargs = scheduled_jobs[0]
    task(*args, **kwargs)

    assert execution_service.calls == [("demo", 18)]
    assert reconciliation_service.calls == 1


def test_start_implementation_issue_endpoint_rejects_unclaimed_issue(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    worktree_root.mkdir(parents=True)
    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses=build_config().harnesses,
    )
    unclaimed_issue = GitHubIssueRecord(
        number=18,
        title="Implementation child",
        body=(
            "## Parent PRD\n#15\n\n"
            "## What to Build\nBuild it.\n\n"
            "## Acceptance Criteria\n- [ ] Done.\n\n"
            "## Blocked By\nNone\n"
        ),
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issue_gateway = FakeIssueGateway(unclaimed_issue)
    scheduled_jobs: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: issue_gateway,
        background_task_scheduler=lambda task, *args, **kwargs: scheduled_jobs.append(
            (task, args, kwargs)
        ),
    )

    response = TestClient(app).post("/dashboard/repos/demo/implementation-issues/18/start")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Implementation Issue is not claimed."
    }
    assert scheduled_jobs == []


def test_start_implementation_issue_endpoint_rejects_missing_worktree(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    worktree_root.mkdir(parents=True)
    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses=build_config().harnesses,
    )
    issue_gateway = FakeIssueGateway(build_claimed_issue())
    scheduled_jobs: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: issue_gateway,
        background_task_scheduler=lambda task, *args, **kwargs: scheduled_jobs.append(
            (task, args, kwargs)
        ),
    )

    response = TestClient(app).post("/dashboard/repos/demo/implementation-issues/18/start")

    assert response.status_code == 400
    assert response.json() == {
        "detail": f"Implementation Issue worktree does not exist: {worktree_root / 'issue-18'}"
    }
    assert scheduled_jobs == []


def test_start_implementation_issue_endpoint_returns_server_error_for_unexpected_issue_lookup_failure(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    worktree_root.mkdir(parents=True)
    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses=build_config().harnesses,
    )

    class FailingIssueGateway:
        def view_issue(self, number: int) -> GitHubIssueRecord:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: FailingIssueGateway(),
    )

    response = TestClient(app).post("/dashboard/repos/demo/implementation-issues/18/start")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Implementation issue start failed for repo 'demo': GitHub issue access failed"
    }


def test_integrate_implementation_issue_endpoint_returns_branch_metadata_on_success() -> None:
    service = FakeIntegrationService(
        IntegrationResult(
            issue_number=18,
            status="succeeded",
            implementation_branch="impl/15/18-add-implementation-issue-claim-dashboard-control",
            prd_branch="prd/15-add-interactive-dashboard-backend-control-apis",
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        integration_service_factory=lambda repo: service,
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/integrate"
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "repo": "demo",
        "action": "integrate-implementation-issue",
        "status": "integrated",
        "issue_number": 18,
        "implementation_branch": "impl/15/18-add-implementation-issue-claim-dashboard-control",
        "prd_branch": "prd/15-add-interactive-dashboard-backend-control-apis",
    }
    assert service.calls == [
        ("/repos/demo", "/worktrees/demo", 18)
    ]


def test_integrate_implementation_issue_endpoint_returns_bad_request_for_known_failure() -> None:
    service = FakeIntegrationService(
        IntegrationResult(
            issue_number=18,
            status="failed",
            failure_type="merge_conflict",
            failure_message="Merge conflict while updating implementation branch against PRD branch:\nconflict",
            implementation_branch="impl/15/18-add-implementation-issue-claim-dashboard-control",
            prd_branch="prd/15-add-interactive-dashboard-backend-control-apis",
        )
    )
    app = create_dashboard_app(
        config=build_config(),
        integration_service_factory=lambda repo: service,
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/integrate"
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Merge conflict while updating implementation branch against PRD branch:\nconflict"
    }


def test_integrate_implementation_issue_endpoint_preserves_deliberate_not_found_errors() -> None:
    class MissingIntegrationService:
        def integrate_issue(
            self, *, repo_path: str, worktree_root: str, issue_number: int
        ) -> IntegrationResult:
            raise HTTPException(
                status_code=404,
                detail="Implementation Issue worktree does not exist.",
            )

    app = create_dashboard_app(
        config=build_config(),
        integration_service_factory=lambda repo: MissingIntegrationService(),
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/integrate"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Implementation Issue worktree does not exist."
    }


def test_integrate_implementation_issue_endpoint_returns_not_found_for_unknown_repo() -> None:
    app = create_dashboard_app(config=build_config())

    response = TestClient(app).post(
        "/dashboard/repos/missing/implementation-issues/18/integrate"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Unknown repo 'missing'. Available repos: demo."
    }


def test_integrate_implementation_issue_endpoint_returns_server_error_for_unexpected_failure() -> None:
    class FailingIntegrationService:
        def integrate_issue(
            self, *, repo_path: str, worktree_root: str, issue_number: int
        ) -> IntegrationResult:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=build_config(),
        integration_service_factory=lambda repo: FailingIntegrationService(),
    )

    response = TestClient(app).post(
        "/dashboard/repos/demo/implementation-issues/18/integrate"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Implementation issue integration failed for repo 'demo': GitHub issue access failed"
    }
