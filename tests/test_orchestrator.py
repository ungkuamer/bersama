from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from bersama.config import AppConfig, RepoConfig
from bersama.github_issues import GitHubIssueRecord
from bersama.orchestrator import Orchestrator
from bersama.claiming import ClaimResult
from bersama.execution import ExecutionResult
from bersama.integration import IntegrationResult


class FakeExecutor:
    """Deterministic fake executor that runs tasks synchronously and records submissions."""

    def __init__(self) -> None:
        self.submitted: list[tuple] = []
        self._shutdown_called = False

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        result = fn(*args, **kwargs)
        future: Future = Future()
        future.set_result(result)
        return future

    def shutdown(self, wait: bool = True) -> None:
        self._shutdown_called = True


def test_prepare_unprepared_prd() -> None:
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="New PRD Feature",
        body="Some description",
        labels=("prd",),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record,)

    orchestrator = Orchestrator(issues_gateway=issues_gateway)
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.execution_service = MagicMock()
    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # 1. Reconciliation service reconcile was called at the start
    orchestrator.reconciliation_service.reconcile.assert_any_call()

    # 2. PRD preparation service was called to prepare the issue
    orchestrator.prd_preparation_service.prepare_issue.assert_called_once_with(
        repo_path="/repos/demo",
        main_branch="main",
        issue_number=1,
    )


def test_claim_execute_integrate_workflow() -> None:
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_record = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record, impl_record)

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-123",
        implementation_branch="impl/1/2-implementation-child",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2,
        status="succeeded",
        exit_code=0,
        new_commits=True,
        log_path="/worktrees/demo/issue-2/harness.log",
        run_state_path="/worktrees/demo/issue-2/run-state.json",
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2,
        status="succeeded",
        implementation_branch="impl/1/2-implementation-child",
        prd_branch="prd/1-prepared-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # 1. prepare_issue was NOT called since it already has a prd_branch
    orchestrator.prd_preparation_service.prepare_issue.assert_not_called()

    # 2. claim_issue was called for issue 2
    orchestrator.claim_service.claim_issue.assert_called_once()

    # 3. execute_run was called for issue 2
    orchestrator.execution_service.execute_run.assert_called_once_with(
        repo_name="demo",
        issue_number=2,
        config=config,
    )

    # 4. integrate_issue was called for issue 2
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=2,
    )

    # 5. reconcile was called at start and end
    assert orchestrator.reconciliation_service.reconcile.call_count == 2


def test_claim_fails_execution_stops_integration() -> None:
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_record = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record, impl_record)

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-123",
        implementation_branch="impl/1/2-implementation-child",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2,
        status="failed",
        exit_code=1,
        new_commits=False,
        failure_reason="Harness exited with code 1",
    )

    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Verify execute_run was called, but integrate_issue was NOT called!
    orchestrator.claim_service.claim_issue.assert_called_once()
    orchestrator.execution_service.execute_run.assert_called_once()
    orchestrator.integration_service.integrate_issue.assert_not_called()


def test_continuous_loop_execution_workflow() -> None:
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_record = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    
    # First plan/list has a ready issue; second plan/list has none (simulating issue being claimed/closed)
    issues_gateway.list_issues.side_effect = [
        (prd_record, impl_record),  # start reconciliation
        (prd_record, impl_record),  # plan actions
        (prd_record,),              # second loop start reconciliation
        (prd_record,),              # second loop plan actions
    ]

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-123",
        implementation_branch="impl/1/2-implementation-child",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2,
        status="succeeded",
        exit_code=0,
        new_commits=True,
        log_path="/worktrees/demo/issue-2/harness.log",
        run_state_path="/worktrees/demo/issue-2/run-state.json",
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2,
        status="succeeded",
        implementation_branch="impl/1/2-implementation-child",
        prd_branch="prd/1-prepared-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    # Run in continuous mode
    orchestrator.run("demo", config, continuous=True)

    # Verify claim_issue, execute_run and integrate_issue were called in the first loop
    orchestrator.claim_service.claim_issue.assert_called_once()
    orchestrator.execution_service.execute_run.assert_called_once()
    orchestrator.integration_service.integrate_issue.assert_called_once()

    # Reconcile should have run: start and end of loop 1, plus start and end of loop 2 -> 4 times total!
    assert orchestrator.reconciliation_service.reconcile.call_count == 4


def test_bounded_concurrent_scheduling_pass_dispatches_multiple_issues() -> None:
    issues_gateway = MagicMock()

    # Two PRDs, both prepared
    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    prd_2 = GitHubIssueRecord(
        number=2,
        title="PRD 2",
        body="## Problem Statement\n\nMore work.\n\n## Orchestration\n- PRD Branch: prd/2-prd-2",
        labels=("prd",),
        state="open",
    )
    # Two implementation issues from different PRDs, both ready
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl for PRD 1",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_4 = GitHubIssueRecord(
        number=4,
        title="Impl for PRD 2",
        body="## Parent PRD\n#2\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, prd_2, impl_3, impl_4)

    fake_executor = FakeExecutor()

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        executor=fake_executor,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(
            issue_number=3,
            agent_run_id="run-aaa",
            implementation_branch="impl/1/3-impl-for-prd-1",
            worktree_path="/worktrees/demo/issue-3",
        ),
        ClaimResult(
            issue_number=4,
            agent_run_id="run-bbb",
            implementation_branch="impl/2/4-impl-for-prd-2",
            worktree_path="/worktrees/demo/issue-4",
        ),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(
            issue_number=3,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
        ExecutionResult(
            issue_number=4,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.side_effect = [
        IntegrationResult(issue_number=3, status="succeeded", implementation_branch="impl/1/3-impl-for-prd-1", prd_branch="prd/1-prd-1"),
        IntegrationResult(issue_number=4, status="succeeded", implementation_branch="impl/2/4-impl-for-prd-2", prd_branch="prd/2-prd-2"),
    ]

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Both claimable issues should have been dispatched to the executor
    assert len(fake_executor.submitted) == 2

    # Both should have been claimed, executed, and integrated
    assert orchestrator.claim_service.claim_issue.call_count == 2
    assert orchestrator.execution_service.execute_run.call_count == 2
    assert orchestrator.integration_service.integrate_issue.call_count == 2


def test_claim_failure_does_not_block_other_concurrent_issues() -> None:
    issues_gateway = MagicMock()

    # Two PRDs, both prepared
    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    prd_2 = GitHubIssueRecord(
        number=2,
        title="PRD 2",
        body="## Problem Statement\n\nMore work.\n\n## Orchestration\n- PRD Branch: prd/2-prd-2",
        labels=("prd",),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl for PRD 1",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_4 = GitHubIssueRecord(
        number=4,
        title="Impl for PRD 2",
        body="## Parent PRD\n#2\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, prd_2, impl_3, impl_4)

    fake_executor = FakeExecutor()

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        executor=fake_executor,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    # Issue 3's claim fails, issue 4's claim succeeds
    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(
            issue_number=3,
            agent_run_id=None,
            implementation_branch=None,
            worktree_path=None,
            failure_message="PRD is not prepared",
        ),
        ClaimResult(
            issue_number=4,
            agent_run_id="run-bbb",
            implementation_branch="impl/2/4-impl-for-prd-2",
            worktree_path="/worktrees/demo/issue-4",
        ),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=4,
        status="succeeded",
        exit_code=0,
        new_commits=True,
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=4,
        status="succeeded",
        implementation_branch="impl/2/4-impl-for-prd-2",
        prd_branch="prd/2-prd-2",
    )

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Both dispatched to executor
    assert len(fake_executor.submitted) == 2

    # Claim was attempted for both, but only one succeeded
    assert orchestrator.claim_service.claim_issue.call_count == 2

    # Only issue 4 should have been executed and integrated
    assert orchestrator.execution_service.execute_run.call_count == 1
    orchestrator.execution_service.execute_run.assert_called_once_with(
        repo_name="demo",
        issue_number=4,
        config=config,
    )
    assert orchestrator.integration_service.integrate_issue.call_count == 1
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=4,
    )

