from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from bersama.config import AppConfig, RepoConfig
from bersama.github_issues import GitHubIssueRecord
from bersama.orchestrator import Orchestrator
from bersama.claiming import ClaimResult
from bersama.execution import ExecutionResult
from bersama.integration import IntegrationResult


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
