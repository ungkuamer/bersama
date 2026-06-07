import json
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rangkai.claiming import ClaimResult
from rangkai.command_executor import CommandExecutor
from rangkai.config import AppConfig, HarnessConfig, RepoConfig, QualityGateConfig
from rangkai.dashboard import create_dashboard_app
from rangkai.event_bus import Event
from rangkai.execution import ExecutionResult
from rangkai.file_watcher import FileWatcherService
from rangkai.github_issues import GitHubIssueGateway, GitHubIssueRecord
from rangkai.integration import IntegrationResult
from rangkai.prd_preparation import PrdPreparationResult
from rangkai.repo_lock import RepoLock


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


class FakeSchedulingReadinessProvider:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self.calls: list[str] = []
        self._snapshot = snapshot

    def build_snapshot(self, repo_name: str) -> dict[str, object]:
        self.calls.append(repo_name)
        return self._snapshot


class FakeFileWatcherService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


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


def build_unclaimed_issue() -> GitHubIssueRecord:
    return GitHubIssueRecord(
        number=19,
        title="Unclaimed implementation child",
        body=(
            "## Parent PRD\n"
            "#15\n\n"
            "## What to Build\n"
            "Build it later.\n\n"
            "## Acceptance Criteria\n"
            "- [ ] Done.\n\n"
            "## Blocked By\n"
            "None\n\n"
            "## Orchestration\n"
            "- Implementation Branch: impl/15/19-unclaimed-implementation-child\n"
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


def test_dashboard_app_starts_and_stops_file_watcher_with_lifecycle() -> None:
    watcher = FakeFileWatcherService()
    app = create_dashboard_app(
        config=build_config(),
        file_watcher_factory=lambda event_bus, worktree_roots: watcher,
    )

    with TestClient(app):
        assert watcher.start_calls == 1
        assert app.state.file_watcher is watcher

    assert watcher.stop_calls == 1


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


def test_default_dashboard_service_factory_builds_bounded_issue_gateway() -> None:
    created_gateways: list[GitHubIssueGateway] = []

    def fake_gateway_factory(*, cwd=None) -> GitHubIssueGateway:
        gateway = GitHubIssueGateway(cwd=cwd)
        created_gateways.append(gateway)
        return gateway

    with patch("rangkai.dashboard.create_bounded_issue_gateway", side_effect=fake_gateway_factory), patch(
        "rangkai.dashboard.ReconciliationService.reconcile", return_value=None
    ):
        client = TestClient(create_dashboard_app(config=build_config()))
        response = client.post("/dashboard/repos/demo/reconcile")

    assert response.status_code == 200
    assert len(created_gateways) == 1
    assert created_gateways[0]._cwd == Path("/repos/demo")


def test_default_dashboard_service_factories_bind_repo_lock_to_internal_workspaces() -> None:
    captured_workspaces: dict[str, object] = {}

    class RecordingPrdPreparationService:
        def __init__(self, *, issues: object, workspace: object) -> None:
            del issues
            captured_workspaces["prd"] = workspace

        def prepare_issue(
            self, *, repo_path: str, main_branch: str, issue_number: int
        ) -> PrdPreparationResult:
            del repo_path, main_branch, issue_number
            return PrdPreparationResult(
                issue_number=15,
                prd_branch="prd/15-demo",
                reused_existing_branch=False,
                updated_issue_body=True,
            )

    class RecordingClaimService:
        def __init__(self, *, issues: object, workspace: object, now_provider: object = None) -> None:
            del issues, now_provider
            captured_workspaces["claim"] = workspace

        def claim_issue(
            self,
            *,
            repo_path: str,
            worktree_root: str,
            issue_number: int,
            agent_run_id: str,
        ) -> ClaimResult:
            del repo_path, worktree_root, issue_number, agent_run_id
            return ClaimResult(
                issue_number=18,
                agent_run_id="run-123",
                implementation_branch="impl/15/18-demo",
                worktree_path="/worktrees/demo/issue-18",
            )

    class RecordingIntegrationService:
        def __init__(self, *, issues: object, workspace: object) -> None:
            del issues
            captured_workspaces["integration"] = workspace

        def integrate_issue(
            self, *, repo_path: str, worktree_root: str, issue_number: int
        ) -> IntegrationResult:
            del repo_path, worktree_root, issue_number
            return IntegrationResult(
                issue_number=18,
                status="succeeded",
                implementation_branch="impl/15/18-demo",
                prd_branch="prd/15-demo",
            )

    with patch("rangkai.dashboard.PrdPreparationService", RecordingPrdPreparationService), patch(
        "rangkai.dashboard.ImplementationClaimService", RecordingClaimService
    ), patch("rangkai.dashboard.IntegrationService", RecordingIntegrationService):
        client = TestClient(create_dashboard_app(config=build_config()))
        assert client.post("/dashboard/repos/demo/prd-issues/15/prepare").status_code == 200
        assert client.post(
            "/dashboard/repos/demo/implementation-issues/18/claim",
            json={"agent_run_id": "run-123"},
        ).status_code == 200
        assert client.post(
            "/dashboard/repos/demo/implementation-issues/18/integrate"
        ).status_code == 200

    for key in ("prd", "claim", "integration"):
        workspace = captured_workspaces[key]
        assert isinstance(workspace._lock, RepoLock)
        assert workspace._lock._repo_path == "/repos/demo"


def test_default_dashboard_service_factories_inject_command_executor_into_workspace_gateways() -> None:
    captured_workspaces: dict[str, object] = {}

    class RecordingPrdPreparationService:
        def __init__(self, *, issues: object, workspace: object) -> None:
            del issues
            captured_workspaces["prd"] = workspace

        def prepare_issue(
            self, *, repo_path: str, main_branch: str, issue_number: int
        ) -> PrdPreparationResult:
            del repo_path, main_branch, issue_number
            return PrdPreparationResult(
                issue_number=15,
                prd_branch="prd/15-demo",
                reused_existing_branch=False,
                updated_issue_body=True,
            )

    class RecordingClaimService:
        def __init__(self, *, issues: object, workspace: object, now_provider: object = None) -> None:
            del issues, now_provider
            captured_workspaces["claim"] = workspace

        def claim_issue(
            self,
            *,
            repo_path: str,
            worktree_root: str,
            issue_number: int,
            agent_run_id: str,
        ) -> ClaimResult:
            del repo_path, worktree_root, issue_number, agent_run_id
            return ClaimResult(
                issue_number=18,
                agent_run_id="run-123",
                implementation_branch="impl/15/18-demo",
                worktree_path="/worktrees/demo/issue-18",
            )

    class RecordingIntegrationService:
        def __init__(self, *, issues: object, workspace: object) -> None:
            del issues
            captured_workspaces["integration"] = workspace

        def integrate_issue(
            self, *, repo_path: str, worktree_root: str, issue_number: int
        ) -> IntegrationResult:
            del repo_path, worktree_root, issue_number
            return IntegrationResult(
                issue_number=18,
                status="succeeded",
                implementation_branch="impl/15/18-demo",
                prd_branch="prd/15-demo",
            )

    with patch("rangkai.dashboard.PrdPreparationService", RecordingPrdPreparationService), patch(
        "rangkai.dashboard.ImplementationClaimService", RecordingClaimService
    ), patch("rangkai.dashboard.IntegrationService", RecordingIntegrationService):
        client = TestClient(create_dashboard_app(config=build_config()))
        client.post("/dashboard/repos/demo/prd-issues/15/prepare")
        client.post(
            "/dashboard/repos/demo/implementation-issues/18/claim",
            json={"agent_run_id": "run-123"},
        )
        client.post("/dashboard/repos/demo/implementation-issues/18/integrate")

    for key in ("prd", "claim", "integration"):
        workspace = captured_workspaces[key]
        assert isinstance(workspace._command_executor, CommandExecutor)


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


def test_get_repos_endpoint_returns_repos() -> None:
    app = create_dashboard_app(config=build_config())
    response = TestClient(app).get("/api/repos")
    assert response.status_code == 200
    repos = response.json()
    assert len(repos) == 1
    assert repos[0]["name"] == "demo"
    assert repos[0]["main_branch"] == "main"


def test_get_issues_endpoint_returns_hierarchical_issues() -> None:
    class CustomFakeIssueGateway:
        def __init__(self, *issues: GitHubIssueRecord) -> None:
            self.issues = {issue.number: issue for issue in issues}

        def list_issues(
            self,
            *,
            state: str = "open",
            label: str | None = None,
            labels: tuple[str, ...] | None = None,
            updated_since: str | None = None,
        ) -> list[GitHubIssueRecord]:
            result = list(self.issues.values())
            if labels is not None:
                label_set = set(labels)
                result = [r for r in result if set(r.labels) & label_set]
            if state != "all":
                result = [r for r in result if r.state == state]
            return result

        def view_issue(self, number: int) -> GitHubIssueRecord:
            return self.issues[number]

    prd_issue = GitHubIssueRecord(
        number=15,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )
    impl_issue = build_claimed_issue()
    app = create_dashboard_app(
        config=build_config(),
        issue_gateway_factory=lambda: CustomFakeIssueGateway(prd_issue, impl_issue),
    )
    response = TestClient(app).get("/api/issues?repo=demo")
    assert response.status_code == 200
    issues = response.json()
    assert len(issues) == 1
    assert issues[0]["number"] == 15
    assert len(issues[0]["children"]) == 1
    assert issues[0]["children"][0]["number"] == 18
    assert issues[0]["children"][0]["status"] == "claimed"
    assert issues[0]["children"][0]["agent_run_id"] == "run-123"
    assert issues[0]["children"][0]["claimed_at"] == "2026-05-29T20:07:02Z"


def test_get_issues_endpoint_does_not_falsely_mark_unclaimed_issue_as_claimed() -> None:
    class CustomFakeIssueGateway:
        def __init__(self, *issues: GitHubIssueRecord) -> None:
            self.issues = {issue.number: issue for issue in issues}

        def list_issues(
            self,
            *,
            state: str = "open",
            label: str | None = None,
            labels: tuple[str, ...] | None = None,
            updated_since: str | None = None,
        ) -> list[GitHubIssueRecord]:
            result = list(self.issues.values())
            if labels is not None:
                label_set = set(labels)
                result = [r for r in result if set(r.labels) & label_set]
            if state != "all":
                result = [r for r in result if r.state == state]
            return result

        def view_issue(self, number: int) -> GitHubIssueRecord:
            return self.issues[number]

    prd_issue = GitHubIssueRecord(
        number=15,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )
    impl_issue = build_unclaimed_issue()
    app = create_dashboard_app(
        config=build_config(),
        issue_gateway_factory=lambda: CustomFakeIssueGateway(prd_issue, impl_issue),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    child = response.json()[0]["children"][0]
    assert child["number"] == 19
    assert child["status"] == "unready"
    assert child["agent_run_id"] is None
    assert child["claimed_at"] is None


def test_get_issues_endpoint_returns_malformed_implementation_issue_with_diagnostics() -> None:
    class CustomFakeIssueGateway:
        def __init__(self, *issues: GitHubIssueRecord) -> None:
            self.issues = {issue.number: issue for issue in issues}

        def list_issues(
            self,
            *,
            state: str = "open",
            label: str | None = None,
            labels: tuple[str, ...] | None = None,
            updated_since: str | None = None,
        ) -> list[GitHubIssueRecord]:
            result = list(self.issues.values())
            if labels is not None:
                label_set = set(labels)
                result = [r for r in result if set(r.labels) & label_set]
            if state != "all":
                result = [r for r in result if r.state == state]
            return result

    prd_issue = GitHubIssueRecord(
        number=15,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )
    malformed_impl_issue = GitHubIssueRecord(
        number=18,
        title="Malformed implementation child",
        body=(
            "## Parent PRD\n"
            "#15\n\n"
            "## What to Build\n"
            "Build it.\n"
        ),
        labels=("implementation",),
        state="open",
    )
    app = create_dashboard_app(
        config=build_config(),
        issue_gateway_factory=lambda: CustomFakeIssueGateway(prd_issue, malformed_impl_issue),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    child = response.json()[0]["children"][0]
    assert child["number"] == 18
    assert child["status"] == "degraded"
    assert child["diagnostics"] == [
        {
            "code": "missing-acceptance-criteria",
            "kind": "missing-info",
            "message": "Missing Acceptance Criteria section.",
        },
        {
            "code": "missing-blocked-by",
            "kind": "missing-info",
            "message": "Missing Blocked By section.",
        },
    ]


def test_get_issues_endpoint_returns_malformed_prd_issue_with_diagnostics() -> None:
    class CustomFakeIssueGateway:
        def __init__(self, *issues: GitHubIssueRecord) -> None:
            self.issues = {issue.number: issue for issue in issues}

        def list_issues(
            self,
            *,
            state: str = "open",
            label: str | None = None,
            labels: tuple[str, ...] | None = None,
            updated_since: str | None = None,
        ) -> list[GitHubIssueRecord]:
            result = list(self.issues.values())
            if labels is not None:
                label_set = set(labels)
                result = [r for r in result if set(r.labels) & label_set]
            if state != "all":
                result = [r for r in result if r.state == state]
            return result

    malformed_prd_issue = GitHubIssueRecord(
        number=15,
        title="Malformed PRD Title",
        body="",
        labels=("prd", "implementation"),
        state="open",
    )
    app = create_dashboard_app(
        config=build_config(),
        issue_gateway_factory=lambda: CustomFakeIssueGateway(malformed_prd_issue),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    assert response.json() == [
        {
            "number": 15,
            "title": "Malformed PRD Title",
            "labels": ["prd", "implementation"],
            "state": "open",
            "kind": "unknown",
            "status": "degraded",
            "diagnostics": [
                {
                    "code": "ambiguous-issue-kind",
                    "kind": "invalid-state",
                    "message": "Issue cannot be both a PRD Issue and an Implementation Issue.",
                }
            ],
        }
    ]


def test_get_issues_endpoint_returns_server_error_for_listing_failure() -> None:
    class FailingIssueGateway:
        def list_issues(
            self,
            *,
            state: str = "open",
            label: str | None = None,
            labels: tuple[str, ...] | None = None,
            updated_since: str | None = None,
        ) -> list[GitHubIssueRecord]:
            raise RuntimeError("GitHub issue access failed")

    app = create_dashboard_app(
        config=build_config(),
        issue_gateway_factory=lambda: FailingIssueGateway(),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Failed to list GitHub issues: GitHub issue access failed"
    }


def test_get_runs_endpoint_scans_worktree(tmp_path: Path) -> None:
    import json
    from dataclasses import replace
    config = build_config()
    config.repos["demo"] = replace(config.repos["demo"], worktree_root=tmp_path)
    
    issue_dir = tmp_path / "issue-18"
    issue_dir.mkdir(parents=True)
    run_state = {
        "status": "running",
        "issue_number": 18,
        "prd_branch": "prd/15",
        "implementation_branch": "impl/18",
        "started_at": "2026-05-29T20:00:00Z",
    }
    (issue_dir / "run-state.json").write_text(json.dumps(run_state))
    (issue_dir / "harness.log").write_text("Harness execution logtail output")

    app = create_dashboard_app(config=config)
    
    response = TestClient(app).get("/api/runs?repo=demo")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["issue_number"] == 18
    assert runs[0]["status"] == "running"

    log_response = TestClient(app).get("/api/runs/18/log?repo=demo&limit=10")
    assert log_response.status_code == 200
    log_data = log_response.json()
    assert log_data["issue_number"] == 18
    assert log_data["content"] == "Harness execution logtail output"


def test_get_runs_endpoint_returns_degraded_entries_for_corrupt_run_state(
    tmp_path: Path,
) -> None:
    import json
    from dataclasses import replace

    config = build_config()
    config.repos["demo"] = replace(config.repos["demo"], worktree_root=tmp_path)

    valid_issue_dir = tmp_path / "issue-18"
    valid_issue_dir.mkdir(parents=True)
    (valid_issue_dir / "run-state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "issue_number": 18,
                "prd_branch": "prd/15",
                "implementation_branch": "impl/18",
                "started_at": "2026-05-29T20:00:00Z",
            }
        )
    )

    corrupt_issue_dir = tmp_path / "issue-19"
    corrupt_issue_dir.mkdir(parents=True)
    (corrupt_issue_dir / "run-state.json").write_text("{not valid json")

    app = create_dashboard_app(config=config)

    response = TestClient(app).get("/api/runs?repo=demo")

    assert response.status_code == 200
    assert response.json() == [
        {
            "status": "running",
            "issue_number": 18,
            "prd_branch": "prd/15",
            "implementation_branch": "impl/18",
            "started_at": "2026-05-29T20:00:00Z",
        },
        {
            "issue_number": 19,
            "status": "degraded",
            "run_state_path": str(corrupt_issue_dir / "run-state.json"),
            "diagnostics": [
                {
                    "code": "invalid-run-state-json",
                    "kind": "invalid-state",
                    "message": "Run state file is not valid JSON.",
                }
            ],
        },
    ]


def test_get_runs_endpoint_returns_degraded_entries_for_unreadable_run_state(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    config = build_config()
    config.repos["demo"] = replace(config.repos["demo"], worktree_root=tmp_path)

    issue_dir = tmp_path / "issue-22"
    issue_dir.mkdir(parents=True)
    run_state_path = issue_dir / "run-state.json"
    run_state_path.write_text('{"status":"running"}')

    app = create_dashboard_app(config=config)

    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        response = TestClient(app).get("/api/runs?repo=demo")

    assert response.status_code == 200
    assert response.json() == [
        {
            "issue_number": 22,
            "status": "degraded",
            "run_state_path": str(run_state_path),
            "diagnostics": [
                {
                    "code": "unreadable-run-state",
                    "kind": "read-error",
                    "message": "Run state file could not be read.",
                }
            ],
        }
    ]


def test_get_run_log_endpoint_returns_actionable_diagnostics_for_read_failure(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    config = build_config()
    config.repos["demo"] = replace(config.repos["demo"], worktree_root=tmp_path)

    issue_dir = tmp_path / "issue-18"
    issue_dir.mkdir(parents=True)
    log_path = issue_dir / "harness.log"
    log_path.write_text("Harness execution logtail output")

    app = create_dashboard_app(config=config)

    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        response = TestClient(app).get("/api/runs/18/log?repo=demo&limit=10")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "unreadable-run-log",
            "kind": "read-error",
            "message": "Run log file could not be read.",
            "issue_number": 18,
            "log_path": str(log_path),
        }
    }


def test_get_scheduling_readiness_snapshot_returns_normalized_repo_snapshot() -> None:
    provider = FakeSchedulingReadinessProvider(
        {
            "repo": {
                "name": "demo",
                "path": "/repos/demo",
                "main_branch": "main",
                "worktree_root": "/worktrees/demo",
            },
            "snapshot": {
                "observed_at": "2026-05-31T19:00:00Z",
                "config_provenance": {
                    "source": "app-config",
                    "default_harness": {
                        "name": "local",
                        "timeout_seconds": None,
                    },
                },
                "harness_summary": {
                    "default_harness": "local",
                    "timeout_seconds": None,
                },
                "readiness_checks": {
                    "critical_failures": [],
                    "warnings": [],
                },
                "implementation_issue_state": {
                    "items": [],
                    "summary": {
                        "ready": 0,
                        "blocked": 0,
                        "claimed": 0,
                        "running": 0,
                        "failed": 0,
                        "succeeded": 0,
                        "other": 0,
                    },
                },
            },
        }
    )
    app = create_dashboard_app(config=build_config(), scheduling_readiness_provider=provider)

    # Note: Using '/demo' path as mapped in dashboard app
    response = TestClient(app).get("/api/scheduling-readiness/demo")

    assert response.status_code == 200
    assert response.json() == {
        "repo": {
            "name": "demo",
            "path": "/repos/demo",
            "main_branch": "main",
            "worktree_root": "/worktrees/demo",
        },
        "snapshot": {
            "observed_at": response.json()["snapshot"]["observed_at"],
            "config_provenance": {
                "source": "app-config",
                "default_harness": {
                    "name": "local",
                    "timeout_seconds": None,
                },
            },
            "harness_summary": {
                "default_harness": "local",
                "timeout_seconds": None,
            },
            "readiness_checks": {
                "critical_failures": [],
                "warnings": [],
            },
            "implementation_issue_state": {
                "items": [],
                "summary": {
                    "ready": 0,
                    "blocked": 0,
                    "claimed": 0,
                    "running": 0,
                    "failed": 0,
                    "succeeded": 0,
                    "other": 0,
                },
            },
        },
    }


def test_get_scheduling_readiness_snapshot_includes_harness_timeout_when_configured() -> None:
    config = AppConfig(
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
                timeout_seconds=900,
            )
        },
    )
    provider = FakeSchedulingReadinessProvider(
        {
            "repo": {
                "name": "demo",
                "path": "/repos/demo",
                "main_branch": "main",
                "worktree_root": "/worktrees/demo",
            },
            "snapshot": {
                "observed_at": "2026-05-31T19:00:00Z",
                "config_provenance": {
                    "source": "app-config",
                    "default_harness": {
                        "name": "local",
                        "timeout_seconds": 900,
                    },
                },
                "harness_summary": {
                    "default_harness": "local",
                    "timeout_seconds": 900,
                },
                "readiness_checks": {
                    "critical_failures": [],
                    "warnings": [],
                },
                "implementation_issue_state": {
                    "items": [],
                    "summary": {
                        "ready": 0,
                        "blocked": 0,
                        "claimed": 0,
                        "running": 0,
                        "failed": 0,
                        "succeeded": 0,
                        "other": 0,
                    },
                },
            },
        }
    )
    app = create_dashboard_app(config=config, scheduling_readiness_provider=provider)

    response = TestClient(app).get("/api/scheduling-readiness/demo")

    assert response.status_code == 200
    assert response.json()["snapshot"]["harness_summary"] == {
        "default_harness": "local",
        "timeout_seconds": 900,
    }


def test_get_scheduling_readiness_snapshot_returns_actionable_not_found_for_unknown_repo() -> None:
    app = create_dashboard_app(config=build_config())

    response = TestClient(app).get("/api/scheduling-readiness/missing")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Unknown repo 'missing'. Available repos: demo."
    }


def test_get_scheduling_readiness_snapshot_reports_critical_failures_separately_from_warnings() -> None:
    provider = FakeSchedulingReadinessProvider(
        {
            "repo": {
                "name": "demo",
                "path": "/repos/demo",
                "main_branch": "main",
                "worktree_root": "/worktrees/demo",
            },
            "snapshot": {
                "observed_at": "2026-05-31T19:00:00Z",
                "config_provenance": {
                    "source": "app-config",
                    "default_harness": {
                        "name": "local",
                        "timeout_seconds": None,
                    },
                },
                "harness_summary": {
                    "default_harness": "local",
                    "timeout_seconds": None,
                },
                "readiness_checks": {
                    "critical_failures": [
                        {
                            "message": "Required repository labels are missing.",
                            "remediation": "Add the required labels in GitHub before running scheduling.",
                            "details": {
                                "code": "missing-required-labels",
                                "missing_labels": ["claimed", "prd"],
                            },
                        }
                    ],
                    "warnings": [
                        {
                            "message": "Working tree has local changes.",
                            "remediation": "Review local changes before running scheduling.",
                            "details": {
                                "code": "working-tree-dirty",
                            },
                        }
                    ],
                },
                "implementation_issue_state": {
                    "items": [],
                    "summary": {
                        "ready": 0,
                        "blocked": 0,
                        "claimed": 0,
                        "running": 0,
                        "failed": 0,
                        "succeeded": 0,
                        "other": 0,
                    },
                },
            },
        }
    )
    app = create_dashboard_app(
        config=build_config(),
        scheduling_readiness_provider=provider,
    )

    response = TestClient(app).get("/api/scheduling-readiness/demo")

    assert response.status_code == 200
    assert provider.calls == ["demo"]
    assert response.json()["snapshot"]["readiness_checks"] == {
        "critical_failures": [
            {
                "message": "Required repository labels are missing.",
                "remediation": "Add the required labels in GitHub before running scheduling.",
                "details": {
                    "code": "missing-required-labels",
                    "missing_labels": ["claimed", "prd"],
                },
            }
        ],
        "warnings": [
            {
                "message": "Working tree has local changes.",
                "remediation": "Review local changes before running scheduling.",
                "details": {
                    "code": "working-tree-dirty",
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_sse_events_endpoint_streams_published_repo_events() -> None:
    app = create_dashboard_app(config=build_config())
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/events")

    response = await endpoint(repo="demo")

    assert response.media_type == "text/event-stream"
    assert response.status_code == 200

    body_iterator = response.body_iterator
    first_chunk_task = asyncio.create_task(body_iterator.__anext__())

    for _ in range(100):
        if app.state.event_bus._subscribers:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("SSE subscriber did not attach.")

    app.state.event_bus.publish_nowait(
        Event(
            type="issues_updated",
            data={"repo": "demo", "issue_number": 18},
        )
    )

    first_chunk = await asyncio.wait_for(first_chunk_task, timeout=1.0)
    assert first_chunk == {
        "event": "issues_updated",
        "data": json.dumps({"repo": "demo", "issue_number": 18}),
    }


@pytest.mark.asyncio
async def test_sse_events_endpoint_fans_out_to_multiple_subscribers() -> None:
    app = create_dashboard_app(config=build_config())
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/events")

    response_one = await endpoint(repo="demo")
    response_two = await endpoint(repo="demo")

    first_chunk_one = asyncio.create_task(response_one.body_iterator.__anext__())
    first_chunk_two = asyncio.create_task(response_two.body_iterator.__anext__())

    for _ in range(100):
        if len(app.state.event_bus._subscribers) == 2:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("SSE subscribers did not attach.")

    app.state.event_bus.publish_nowait(
        Event(
            type="runs_updated",
            data={"repo": "demo", "issue_number": 18},
        )
    )

    expected = {
        "event": "runs_updated",
        "data": json.dumps({"repo": "demo", "issue_number": 18}),
    }
    assert await asyncio.wait_for(first_chunk_one, timeout=1.0) == expected
    assert await asyncio.wait_for(first_chunk_two, timeout=1.0) == expected


@pytest.mark.asyncio
async def test_sse_events_endpoint_disconnect_removes_subscriber() -> None:
    app = create_dashboard_app(config=build_config())
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/events")

    response = await endpoint(repo="demo")
    iterator = response.body_iterator
    first_chunk_task = asyncio.create_task(iterator.__anext__())

    for _ in range(100):
        if len(app.state.event_bus._subscribers) == 1:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("SSE subscriber did not attach.")

    app.state.event_bus.publish_nowait(
        Event(
            type="issues_updated",
            data={"repo": "demo", "issue_number": 18},
        )
    )
    await asyncio.wait_for(first_chunk_task, timeout=1.0)

    await iterator.aclose()

    for _ in range(100):
        if not app.state.event_bus._subscribers:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("SSE subscriber did not detach.")


def test_quality_gate_api_disabled() -> None:
    # Quality gate is disabled by default in build_config() repo Config
    app = create_dashboard_app(config=build_config())
    response = TestClient(app).get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {"status": "unavailable"}


def test_quality_gate_api_not_run(tmp_path: Path) -> None:
    import dataclasses
    config = build_config()
    # Enable quality gate and set temp worktree root using replace
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )
    
    app = create_dashboard_app(config=config)
    
    # 1. Worktree doesn't exist at all
    response = TestClient(app).get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {"status": "not_run", "message": "Quality gate has not been run."}

    # 2. Worktree exists, but quality-gate folder doesn't exist
    (tmp_path / "issue-18").mkdir(parents=True)
    response = TestClient(app).get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {"status": "not_run", "message": "Quality gate has not been run."}



def test_quality_gate_api_missing_result_json(tmp_path: Path) -> None:
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )
    
    app = create_dashboard_app(config=config)
    client = TestClient(app)
    
    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    
    # Missing result.json produces a "not_run" Quality Gate snapshot with diagnostic message
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "not_run"
    assert "missing" in res_json["message"].lower()


def test_quality_gate_api_access_failure(tmp_path: Path) -> None:
    from unittest.mock import patch
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )
    
    app = create_dashboard_app(config=config)
    client = TestClient(app)
    
    # Mock Path.exists to raise PermissionError
    with patch.object(Path, "exists", side_effect=PermissionError("Permission denied")):
        response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
        assert response.status_code == 500
        res_json = response.json()
        assert res_json["detail"]["code"] == "unreadable-quality-gate"
        assert "permission denied" in res_json["detail"]["message"].lower()


def test_quality_gate_api_states(tmp_path: Path) -> None:
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )
    
    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    # 1. Passed state
    (diag_dir / "result.json").write_text('{"status": "passed", "message": "All checks passed"}')
    (diag_dir / "stdout.txt").write_text("dummy stdout")
    (diag_dir / "stderr.txt").write_text("dummy stderr")
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "passed",
        "message": "All checks passed",
        "checks": [],
        "judge": {"status": "not_run", "message": "Judge Layer has not been run."},
    }

    # 2. Failed state
    (diag_dir / "result.json").write_text('{"status": "failed", "message": "Coverage is 40%"}')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "message": "Coverage is 40%",
        "checks": [],
        "judge": {"status": "not_run", "message": "Judge Layer has not been run."},
    }

    # 3. Error state
    (diag_dir / "result.json").write_text('{"status": "error", "message": "Command not found"}')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "error",
        "message": "Command not found",
        "checks": [],
        "judge": {"status": "not_run", "message": "Judge Layer has not been run."},
    }

    # 4. Invalid JSON state (malformed JSON)
    (diag_dir / "result.json").write_text('{invalid json')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "invalid"
    assert "malformed" in res_json["message"].lower() or "json" in res_json["message"].lower() or "read" in res_json["message"].lower()

    # 5. Invalid schema state (missing status field or not a dictionary)
    (diag_dir / "result.json").write_text('{"message": "Coverage is 40%"}')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "invalid"
    assert "status" in res_json["message"].lower() or "missing" in res_json["message"].lower() or "invalid" in res_json["message"].lower()

    # 6. Invalid schema state (unexpected status field value)
    (diag_dir / "result.json").write_text('{"status": "unknown"}')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "invalid"
    assert "unrecognized" in res_json["message"].lower() or "unknown" in res_json["message"].lower() or "status" in res_json["message"].lower()


def test_quality_gate_api_checks(tmp_path: Path) -> None:
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )
    
    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    # 1. Check normalization with fully populated checks
    result_data = {
        "status": "failed",
        "message": "Some checks failed",
        "checks": [
            {
                "id": "python-lint",
                "name": "Python Lint",
                "type": "python_lint",
                "status": "failed",
                "advisory": True,
                "message": "Ruff failed"
            },
            {
                "id": "python-tests",
                "name": "Python Tests",
                "type": "python_tests",
                "status": "passed",
                "advisory": False,
                "message": None
            }
        ]
    }
    (diag_dir / "result.json").write_text(json.dumps(result_data))
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "message": "Some checks failed",
        "checks": [
            {
                "id": "python-lint",
                "name": "Python Lint",
                "type": "python_lint",
                "status": "failed",
                "advisory": True,
                "message": "Ruff failed"
            },
            {
                "id": "python-tests",
                "name": "Python Tests",
                "type": "python_tests",
                "status": "passed",
                "advisory": False,
                "message": None
            }
        ],
        "judge": {"status": "not_run", "message": "Judge Layer has not been run."},
    }

    # 2. Check normalization with missing checks array
    (diag_dir / "result.json").write_text('{"status": "passed"}')
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    assert response.json() == {
        "status": "passed",
        "checks": [],
        "judge": {"status": "not_run", "message": "Judge Layer has not been run."},
    }

    # 3. Check normalization with partial checks (fallback behavior)
    result_data_partial = {
        "status": "failed",
        "checks": [
            {
                # Only id
                "id": "only-id",
                "status": "failed"
            },
            {
                # Only name
                "name": "only-name",
                "status": "passed",
                "advisory": True
            },
            {
                # Missing name and id, status and type missing
                "type": "some-type"
            }
        ]
    }
    (diag_dir / "result.json").write_text(json.dumps(result_data_partial))
    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "failed"
    assert len(res_json["checks"]) == 3
    
    # Assert specific fallback values
    c1, c2, c3 = res_json["checks"]
    assert c1 == {
        "id": "only-id",
        "name": "only-id",
        "type": None,
        "status": "failed",
        "advisory": False,
        "message": None
    }
    assert c2 == {
        "id": "only-name",
        "name": "only-name",
        "type": None,
        "status": "passed",
        "advisory": True,
        "message": None
    }
    assert c3 == {
        "id": "unknown",
        "name": "unknown",
        "type": "some-type",
        "status": "unknown",
        "advisory": False,
        "message": None
    }


def test_quality_gate_api_judge_layer_summary(tmp_path: Path) -> None:
    """When judge.json exists, the Quality Gate summary API includes a nested Judge Layer summary."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    # Write the existing quality gate result.json
    (diag_dir / "result.json").write_text('{"status": "passed", "message": "All checks passed", "checks": []}')

    # Write the judge layer artifact
    judge_data = {
        "status": "passed",
        "message": "Judge completed: completion score 1.0, all acceptance criteria met.",
    }
    (diag_dir / "judge.json").write_text(json.dumps(judge_data))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["message"] == "All checks passed"
    assert res_json["checks"] == []
    assert "judge" in res_json
    assert res_json["judge"]["status"] == "passed"
    assert "completion score" in res_json["judge"]["message"]


def test_quality_gate_api_judge_layer_missing(tmp_path: Path) -> None:
    """When judge.json does not exist, the response exposes an explicit nested not_run state."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "message": "All checks passed"}')

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["judge"] == {
        "status": "not_run",
        "message": "Judge Layer has not been run.",
    }


def test_quality_gate_api_judge_layer_invalid_json(tmp_path: Path) -> None:
    """When judge.json is malformed, the response surfaces an explicit invalid nested state."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed"}')
    (diag_dir / "judge.json").write_text('{invalid json')

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["judge"]["status"] == "invalid"
    assert "malformed" in res_json["judge"]["message"].lower()


def test_quality_gate_api_judge_layer_missing_status_field(tmp_path: Path) -> None:
    """When judge.json lacks a status field, the response stays safe and marks the Judge Layer invalid."""
    import dataclasses

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path,
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed"}')
    (diag_dir / "judge.json").write_text(json.dumps({"message": "missing status"}))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["judge"] == {
        "status": "invalid",
        "message": "Judge Layer status field is missing in judge.json.",
    }


def test_quality_gate_api_judge_layer_unexpected_schema_still_returns_safe_nested_summary(
    tmp_path: Path,
) -> None:
    """Unexpected Judge Layer schemas should render safely without crashing the dashboard contract."""
    import dataclasses

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path,
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed"}')
    (diag_dir / "judge.json").write_text(
        json.dumps(
            {
                "status": {"nested": "passed"},
                "message": ["not", "a", "string"],
                "model": {"name": "gpt-4o-mini"},
                "started_at": 1234,
            }
        )
    )

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["judge"] == {
        "status": "invalid",
        "message": "Judge Layer status field in judge.json must be a string.",
    }


def test_quality_gate_api_judge_layer_running(tmp_path: Path) -> None:
    """When judge.json has status running, the API exposes it with model/timing metadata."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    judge_data = {
        "status": "running",
        "message": "Judge is evaluating...",
        "model": "gpt-4o-mini",
        "started_at": "2026-06-05T12:00:00Z",
    }
    (diag_dir / "judge.json").write_text(json.dumps(judge_data))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert "judge" in res_json
    assert res_json["judge"]["status"] == "running"
    assert res_json["judge"]["message"] == "Judge is evaluating..."
    assert res_json["judge"]["model"] == "gpt-4o-mini"
    assert res_json["judge"]["started_at"] == "2026-06-05T12:00:00Z"


def test_quality_gate_api_judge_layer_skipped_validation_failed(tmp_path: Path) -> None:
    """When judge.json has status skipped because deterministic validation failed."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "failed", "message": "Lint failed"}')
    judge_data = {
        "status": "skipped",
        "message": "Judge skipped because deterministic validation did not pass.",
    }
    (diag_dir / "judge.json").write_text(json.dumps(judge_data))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "failed"
    assert "judge" in res_json
    assert res_json["judge"]["status"] == "skipped"
    assert "deterministic validation" in res_json["judge"]["message"].lower()


def test_quality_gate_api_judge_layer_skipped_disabled(tmp_path: Path) -> None:
    """When judge.json has status skipped because judge execution is explicitly disabled."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    judge_data = {
        "status": "skipped",
        "message": "Judge skipped because judge execution is disabled (SARINGAN_SKIP_JUDGE=1).",
    }
    (diag_dir / "judge.json").write_text(json.dumps(judge_data))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert "judge" in res_json
    assert res_json["judge"]["status"] == "skipped"
    assert "disabled" in res_json["judge"]["message"].lower()


def test_quality_gate_api_operator_smoke_path_with_wrapper_artifacts(tmp_path: Path) -> None:
    """The operator smoke path can use real wrapper artifacts and the dashboard API together."""
    import dataclasses
    import os
    import subprocess

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path / "worktrees",
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    worktree_path = config.repos["demo"].worktree_root / "issue-18"
    worktree_path.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=worktree_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )
    (worktree_path / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=worktree_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "branch", "prd-test"], cwd=worktree_path, capture_output=True, check=True)
    (worktree_path / "file.txt").write_text("base\nchange\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=worktree_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "change"],
        cwd=worktree_path,
        capture_output=True,
        check=True,
    )

    fake_saringan = tmp_path / "fake-saringan"
    fake_saringan.write_text(
        '#!/usr/bin/env bash\n'
        'if [ "$1" = "validate" ]; then\n'
        '  echo \'{"status":"passed","check_outcomes":[] }\'\n'
        'elif [ "$1" = "judge" ]; then\n'
        '  echo \'{"status":"passed","check_outcomes":[{"id":"contextual_judge","evidence":{"completion_score":1.0,"scope_guard":true,"acceptance_criteria":[{"id":"ac-1","status":"passed","message":"Satisfied"}]}}]}\'\n'
        'else\n'
        '  echo \'{"status":"error","message":"bad command"}\'\n'
        'fi\n',
        encoding="utf-8",
    )
    fake_saringan.chmod(0o755)

    script = Path(__file__).parent.parent / "scripts" / "saringan-quality-gate.sh"
    env = dict(os.environ)
    env["SARINGAN_BIN"] = str(fake_saringan)
    env["SARINGAN_JUDGE_MODEL"] = "fake-model"
    env["SARINGAN_BASE_REF"] = "prd-test"

    wrapper_run = subprocess.run(
        [str(script), str(worktree_path), "18", "prd-test", "impl/15/18-demo"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )

    diag_dir = worktree_path / "quality-gate"
    diag_dir.mkdir(exist_ok=True)
    (diag_dir / "result.json").write_text(wrapper_run.stdout, encoding="utf-8")

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert res_json["checks"] == []
    assert res_json["judge"]["status"] == "passed"
    assert isinstance(res_json["judge"]["started_at"], str)
    assert res_json["judge"]["evidence"] == [
        {
            "id": "contextual_judge",
            "completion_score": 1.0,
            "scope_guard": True,
            "acceptance_criteria": [
                {
                    "id": "ac-1",
                    "status": "passed",
                    "message": "Satisfied",
                }
            ],
        }
    ]
    assert '"id":"contextual_judge"' in res_json["judge"]["raw"]


# ── Judge Layer evidence drilldown tests (issue #167) ──────────────


def test_quality_gate_api_judge_layer_evidence_normalization(tmp_path: Path) -> None:
    """When judge.result.json contains check outcomes, the API normalizes evidence."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed", "message": "Judge passed"}))

    judge_result = {
        "status": "passed",
        "message": "Judge passed",
        "check_outcomes": [
            {
                "id": "contextual_judge",
                "status": "passed",
                "evidence": {
                    "completion_score": 0.92,
                    "scope_guard": True,
                    "acceptance_criteria": [
                        {"id": "ac-1", "status": "passed", "message": "Criterion 1 met"},
                        {"id": "ac-2", "status": "failed", "message": "Criterion 2 missing"},
                    ],
                },
            },
            {
                "id": "security_judge",
                "status": "passed",
                "evidence": {
                    "completion_score": 1.0,
                },
            },
        ],
    }
    (inputs_dir / "judge.result.json").write_text(json.dumps(judge_result))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "passed"
    assert "judge" in res_json
    judge = res_json["judge"]
    assert judge["status"] == "passed"
    assert "evidence" in judge
    evidence = judge["evidence"]
    assert len(evidence) == 2

    # First evidence item
    assert evidence[0]["id"] == "contextual_judge"
    assert evidence[0]["completion_score"] == 0.92
    assert evidence[0]["scope_guard"] is True
    assert len(evidence[0]["acceptance_criteria"]) == 2
    assert evidence[0]["acceptance_criteria"][0] == {"id": "ac-1", "status": "passed", "message": "Criterion 1 met"}
    assert evidence[0]["acceptance_criteria"][1] == {"id": "ac-2", "status": "failed", "message": "Criterion 2 missing"}

    # Second evidence item
    assert evidence[1]["id"] == "security_judge"
    assert evidence[1]["completion_score"] == 1.0
    assert "scope_guard" not in evidence[1]
    assert "acceptance_criteria" not in evidence[1]


def test_quality_gate_api_judge_layer_bounded_raw_and_stderr(tmp_path: Path) -> None:
    """The API returns bounded raw judge JSON and bounded stderr diagnostics."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed", "message": "Judge passed"}))

    judge_result = {"status": "passed", "check_outcomes": [{"id": "judge", "evidence": {"completion_score": 0.85}}]}
    (inputs_dir / "judge.result.json").write_text(json.dumps(judge_result))
    (inputs_dir / "judge.stderr").write_text("Warning: token limit exceeded\nTrace: some trace\n")

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    judge = res_json["judge"]
    assert "raw" in judge
    assert judge["raw"] == json.dumps(judge_result)
    assert "stderr" in judge
    assert "Warning: token limit exceeded" in judge["stderr"]
    assert "Trace: some trace" in judge["stderr"]


def test_quality_gate_api_judge_layer_missing_result_json_no_evidence(tmp_path: Path) -> None:
    """When judge.result.json is missing, judge summary still works but without evidence/raw/stderr."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed", "message": "Judge passed"}))

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    judge = res_json["judge"]
    assert judge["status"] == "passed"
    assert "evidence" not in judge
    assert "raw" not in judge
    assert "stderr" not in judge


def test_quality_gate_api_judge_layer_bounded_stderr_truncation(tmp_path: Path) -> None:
    """The API bounds stderr to a limited number of lines."""
    import dataclasses
    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed"}))
    (inputs_dir / "judge.result.json").write_text('{"status":"passed"}')

    long_stderr = "\n".join([f"Line {i}" for i in range(1, 100)])
    (inputs_dir / "judge.stderr").write_text(long_stderr)

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")
    assert response.status_code == 200
    res_json = response.json()
    judge = res_json["judge"]
    assert "stderr" in judge
    stderr = judge["stderr"]
    assert isinstance(stderr, str)
    # Should be bounded/truncated
    assert stderr.count("\n") < 100


def test_quality_gate_api_judge_layer_bounded_raw_truncation(tmp_path: Path) -> None:
    """Judge raw output is bounded before reaching the browser."""
    import dataclasses

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path,
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed"}))
    oversized_raw = json.dumps({"payload": "x" * 8000})
    (inputs_dir / "judge.result.json").write_text(oversized_raw)

    response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")

    assert response.status_code == 200
    raw = response.json()["judge"]["raw"]
    assert isinstance(raw, str)
    assert len(raw) == 5000


def test_quality_gate_api_judge_layer_inaccessible_result_uses_existing_quality_gate_error_behavior(
    tmp_path: Path,
) -> None:
    """Unreadable nested Judge Layer artifacts should surface via the existing read-error path."""
    import dataclasses
    from unittest.mock import patch

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path,
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed"}))
    (inputs_dir / "judge.result.json").write_text('{"status":"passed"}')

    original_read_text = Path.read_text

    def raising_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "judge.result.json":
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", autospec=True, side_effect=raising_read_text):
        response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "unreadable-quality-gate",
            "kind": "read-error",
            "message": "Repository or worktree access failure on judge.result.json: permission denied",
        }
    }


def test_quality_gate_api_judge_layer_inaccessible_stderr_uses_existing_quality_gate_error_behavior(
    tmp_path: Path,
) -> None:
    """Unreadable Judge Layer stderr should surface via the existing read-error path."""
    import dataclasses
    from unittest.mock import patch

    config = build_config()
    config.repos["demo"] = dataclasses.replace(
        config.repos["demo"],
        quality_gate=QualityGateConfig(enabled=True, command="true"),
        worktree_root=tmp_path,
    )

    app = create_dashboard_app(config=config)
    client = TestClient(app)

    issue_wt = tmp_path / "issue-18"
    diag_dir = issue_wt / "quality-gate"
    diag_dir.mkdir(parents=True)
    inputs_dir = issue_wt / "quality-gate-inputs"
    inputs_dir.mkdir(parents=True)

    (diag_dir / "result.json").write_text('{"status": "passed", "checks": []}')
    (diag_dir / "judge.json").write_text(json.dumps({"status": "passed"}))
    (inputs_dir / "judge.stderr").write_text("warning")

    original_read_text = Path.read_text

    def raising_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "judge.stderr":
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", autospec=True, side_effect=raising_read_text):
        response = client.get("/api/repos/demo/implementation-issues/18/quality-gate")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "unreadable-quality-gate",
            "kind": "read-error",
            "message": "Repository or worktree access failure on judge.stderr: permission denied",
        }
    }
