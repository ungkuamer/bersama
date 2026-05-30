from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from bersama.config import AppConfig, RepoConfig
from bersama.github_issues import GitHubIssueRecord
from bersama.orchestrator import Orchestrator, SchedulerEvent
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


class PassBasedListIssuesMock:
    """A mock list_issues side effect that tracks continuous mode loop passes
    and correctly filters open/closed issues within each pass."""

    def __init__(self, states_sequence) -> None:
        self.states = states_sequence
        self.current_pass = 0
        self.last_was_closed = False

    def __call__(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
    ) -> tuple[GitHubIssueRecord, ...]:
        if state == "closed":
            self.last_was_closed = True
        elif self.last_was_closed:
            self.current_pass = min(self.current_pass + 1, len(self.states) - 1)
            self.last_was_closed = False

        idx = min(self.current_pass, len(self.states) - 1)
        records = self.states[idx]

        filtered = list(records)
        if state != "all":
            filtered = [r for r in filtered if r.state == state]
        if labels is not None:
            label_set = set(labels)
            filtered = [r for r in filtered if set(r.labels) & label_set]
        elif label is not None:
            filtered = [r for r in filtered if label in r.labels]
        return tuple(filtered)





def test_scheduler_emits_claim_attempt_events() -> None:
    """The scheduler emits claim.succeeded and claim.failed events with issue/run context."""
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation (claimable)",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Implementation (unclaimable)",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record, impl_2, impl_3)

    events: list[SchedulerEvent] = []

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        event_emitter=events.append,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    # Issue 2 claim succeeds, issue 3 claim fails
    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(
            issue_number=2,
            agent_run_id="run-aaa",
            implementation_branch="impl/1/2-claimable",
            worktree_path="/worktrees/demo/issue-2",
        ),
        ClaimResult(
            issue_number=3,
            agent_run_id="run-bbb",
            implementation_branch=None,
            worktree_path=None,
            failure_message="PRD is not prepared",
        ),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2, status="succeeded",
        implementation_branch="impl/1/2-claimable", prd_branch="prd/1-prepared-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Collect claim events
    claim_events = [e for e in events if e.event.startswith("claim.")]
    assert len(claim_events) == 4, f"Expected 4 claim events, got {len(claim_events)}"

    # Claim attempt events (before we know outcome) — one per issue
    attempt_events = [e for e in claim_events if e.event == "claim.attempt"]
    assert len(attempt_events) == 2
    # Each attempt carries issue and run context
    for ae in attempt_events:
        assert ae.issue_number in (2, 3)
        assert ae.agent_run_id is not None

    # Claim succeeded event
    succeeded = [e for e in claim_events if e.event == "claim.succeeded"]
    assert len(succeeded) == 1
    assert succeeded[0].issue_number == 2
    assert succeeded[0].status == "succeeded"

    # Claim failed event
    failed = [e for e in claim_events if e.event == "claim.failed"]
    assert len(failed) == 1
    assert failed[0].issue_number == 3
    assert failed[0].status == "failed"
    assert "PRD is not prepared" in (failed[0].detail or "")


def test_scheduler_emits_agent_run_start_and_finish_events() -> None:
    """The scheduler emits agent_run.start and agent_run.finished events."""
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation (succeeds)",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Implementation (fails)",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record, impl_2, impl_3)

    events: list[SchedulerEvent] = []

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        event_emitter=events.append,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(issue_number=2, agent_run_id="run-aaa", implementation_branch="impl/1/2-succeeds", worktree_path="/worktrees/demo/issue-2"),
        ClaimResult(issue_number=3, agent_run_id="run-bbb", implementation_branch="impl/1/3-fails", worktree_path="/worktrees/demo/issue-3"),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True),
        ExecutionResult(issue_number=3, status="failed", exit_code=1, new_commits=False, failure_reason="build error"),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2, status="succeeded", implementation_branch="impl/1/2-succeeds", prd_branch="prd/1-prepared-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2, per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Agent run start events — one per dispatched issue
    start_events = [e for e in events if e.event == "agent_run.start"]
    assert len(start_events) == 2, f"Expected 2 start events, got {len(start_events)}"
    for se in start_events:
        assert se.issue_number in (2, 3)
        assert se.agent_run_id is not None

    # Agent run finished events — one per dispatched issue
    finish_events = [e for e in events if e.event == "agent_run.finished"]
    assert len(finish_events) == 2, f"Expected 2 finish events, got {len(finish_events)}"

    # Successful finish
    success_finish = [e for e in finish_events if e.status == "succeeded"]
    assert len(success_finish) == 1
    assert success_finish[0].issue_number == 2
    assert success_finish[0].agent_run_id is not None

    # Failed finish
    failed_finish = [e for e in finish_events if e.status == "failed"]
    assert len(failed_finish) == 1
    assert failed_finish[0].issue_number == 3
    assert failed_finish[0].detail == "build error"


def test_scheduler_emits_integration_events() -> None:
    """The scheduler emits integration.start and integration.finished events."""
    issues_gateway = MagicMock()

    prd_record = GitHubIssueRecord(
        number=1,
        title="Prepared PRD",
        body="## Problem Statement\n\nParent.\n\n## Orchestration\n- PRD Branch: prd/1-prepared-prd",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_record, impl_2)

    events: list[SchedulerEvent] = []

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        event_emitter=events.append,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2, agent_run_id="run-aaa",
        implementation_branch="impl/1/2-impl", worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2, status="succeeded", exit_code=0, new_commits=True,
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2, status="succeeded",
        implementation_branch="impl/1/2-impl", prd_branch="prd/1-prepared-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2, per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Integration start event
    integ_start = [e for e in events if e.event == "integration.start"]
    assert len(integ_start) == 1, f"Expected 1 integration.start, got {len(integ_start)}"
    assert integ_start[0].issue_number == 2
    assert integ_start[0].agent_run_id is not None

    # Integration finish event
    integ_finish = [e for e in events if e.event == "integration.finished"]
    assert len(integ_finish) == 1, f"Expected 1 integration.finished, got {len(integ_finish)}"
    assert integ_finish[0].issue_number == 2
    assert integ_finish[0].status == "succeeded"


def test_per_issue_failure_events_include_rich_context() -> None:
    """Failure events at any stage (claim, execution, integration) emit
    per-issue events with enough context to distinguish concurrent Agent Runs."""
    issues_gateway = MagicMock()

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
    # Three implementation issues with different failure modes
    impl_3 = GitHubIssueRecord(  # claim fails
        number=3,
        title="Claim fails",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_4 = GitHubIssueRecord(  # execution fails
        number=4,
        title="Execution fails",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_5 = GitHubIssueRecord(  # integration fails
        number=5,
        title="Integration fails",
        body="## Parent PRD\n#2\n\n## What to Build\nBuild it three.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, prd_2, impl_3, impl_4, impl_5)

    events: list[SchedulerEvent] = []

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        event_emitter=events.append,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    # Different per-issue outcomes
    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(issue_number=3, agent_run_id="run-ccc", implementation_branch=None, worktree_path=None, failure_message="Not prepared"),
        ClaimResult(issue_number=4, agent_run_id="run-ddd", implementation_branch="impl/1/4-exec-fails", worktree_path="/worktrees/demo/issue-4"),
        ClaimResult(issue_number=5, agent_run_id="run-eee", implementation_branch="impl/2/5-integ-fails", worktree_path="/worktrees/demo/issue-5"),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=4, status="failed", exit_code=1, new_commits=False, failure_reason="build error"),
        ExecutionResult(issue_number=5, status="succeeded", exit_code=0, new_commits=True),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=5, status="failed", failure_type="merge_conflict", failure_message="CONFLICT in file.txt",
    )

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=3, per_prd_concurrency=3,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # ── Per-issue events ────────────────────────────────────────────
    # Each issue number appears across multiple events
    for issue_num in (3, 4, 5):
        issue_events = [e for e in events if e.issue_number == issue_num]
        assert len(issue_events) > 0, f"Issue #{issue_num} should have events"

    # Claim failure for issue #3
    issue_3_events = [e for e in events if e.issue_number == 3]
    assert any(e.event == "claim.attempt" for e in issue_3_events)
    assert any(e.event == "claim.failed" for e in issue_3_events)
    # No agent_run or integration events for issue #3 (claim failed early)
    assert not any(e.event.startswith("agent_run.") for e in issue_3_events)
    assert not any(e.event.startswith("integration.") for e in issue_3_events)

    # Execution failure for issue #4
    issue_4_events = [e for e in events if e.issue_number == 4]
    assert any(e.event == "agent_run.start" for e in issue_4_events)
    assert any(e.event == "agent_run.finished" and e.status == "failed" for e in issue_4_events)
    # No integration events for issue #4 (execution failed)
    assert not any(e.event.startswith("integration.") for e in issue_4_events)

    # Integration failure for issue #5
    issue_5_events = [e for e in events if e.issue_number == 5]
    assert any(e.event == "agent_run.start" for e in issue_5_events)
    assert any(e.event == "agent_run.finished" and e.status == "succeeded" for e in issue_5_events)
    assert any(e.event == "integration.start" for e in issue_5_events)
    assert any(e.event == "integration.finished" and e.status == "failed" for e in issue_5_events)

    # ── Concurrent run context ───────────────────────────────────────
    # Each Agent Run has a unique agent_run_id
    run_ids: set[str] = set()
    for e in events:
        if e.agent_run_id:
            run_ids.add(e.agent_run_id)
    # At least 3 unique run IDs (one per dispatched issue)
    assert len(run_ids) >= 3, f"Expected >=3 unique run IDs, got {len(run_ids)}: {run_ids}"

    # Events for different issues don't share the same agent_run_id
    # (Each run is a distinct execution)
    for run_id in run_ids:
        run_issues = {e.issue_number for e in events if e.agent_run_id == run_id}
        assert len(run_issues) == 1, f"Run {run_id} spans multiple issues: {run_issues}"


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
    
    issues_gateway.list_issues.side_effect = PassBasedListIssuesMock([
        (prd_record, impl_record),
        (prd_record,),
    ])


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

    # Reconcile runs: orchestrator start, after drain (meaningful outcome), orchestrator end.
    assert orchestrator.reconciliation_service.reconcile.call_count == 3


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


def test_failed_agent_run_does_not_block_other_concurrent_issues() -> None:
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

    # Issue 3's execution fails, issue 4's execution succeeds
    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(
            issue_number=3,
            status="failed",
            exit_code=1,
            new_commits=False,
            failure_reason="Harness exited with code 1",
        ),
        ExecutionResult(
            issue_number=4,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
    ]

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

    # Both issues dispatched to executor
    assert len(fake_executor.submitted) == 2

    # Both claimed
    assert orchestrator.claim_service.claim_issue.call_count == 2

    # Both executed (the failing one still ran)
    assert orchestrator.execution_service.execute_run.call_count == 2

    # Only issue 4 (successful) should be integrated
    assert orchestrator.integration_service.integrate_issue.call_count == 1
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=4,
    )


def test_needs_info_outcome_does_not_attempt_integration() -> None:
    issues_gateway = MagicMock()

    # One PRD, prepared
    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    # Two implementation issues, both ready
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Impl that needs info",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl that succeeds",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2, impl_3)

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
            issue_number=2,
            agent_run_id="run-aaa",
            implementation_branch="impl/1/2-impl-that-needs-info",
            worktree_path="/worktrees/demo/issue-2",
        ),
        ClaimResult(
            issue_number=3,
            agent_run_id="run-bbb",
            implementation_branch="impl/1/3-impl-that-succeeds",
            worktree_path="/worktrees/demo/issue-3",
        ),
    ]

    # Issue 2 gets paused (needs-info), issue 3 succeeds
    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(
            issue_number=2,
            status="paused",
            exit_code=0,
            new_commits=False,
        ),
        ExecutionResult(
            issue_number=3,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=3,
        status="succeeded",
        implementation_branch="impl/1/3-impl-that-succeeds",
        prd_branch="prd/1-prd-1",
    )

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Both dispatched
    assert len(fake_executor.submitted) == 2

    # Both claimed
    assert orchestrator.claim_service.claim_issue.call_count == 2

    # Both executed
    assert orchestrator.execution_service.execute_run.call_count == 2

    # Only issue 3 (succeeded) should be integrated
    assert orchestrator.integration_service.integrate_issue.call_count == 1
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=3,
    )


def test_execution_exception_does_not_block_concurrent_issues() -> None:
    """When execute_run raises an exception for one issue, other concurrent issues still proceed."""
    issues_gateway = MagicMock()

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

    # Issue 3's execution raises an exception, issue 4's execution succeeds
    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        RuntimeError("Harness process crashed unexpectedly"),
        ExecutionResult(
            issue_number=4,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
    ]

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

    # Should NOT raise - orchestrator handles the exception gracefully
    orchestrator.run("demo", config)

    # Both dispatched to executor
    assert len(fake_executor.submitted) == 2

    # Both claimed
    assert orchestrator.claim_service.claim_issue.call_count == 2

    # Both execute_run calls attempted (first one raised, second succeeded)
    assert orchestrator.execution_service.execute_run.call_count == 2

    # Only issue 4 (succeeded) was integrated
    assert orchestrator.integration_service.integrate_issue.call_count == 1
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=4,
    )


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


def test_execute_claims_tracks_active_agent_runs_in_memory() -> None:
    """The orchestrator tracks dispatched issues as in-memory active runs during execution."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Another child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2, impl_3)

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
            issue_number=2,
            agent_run_id="run-aaa",
            implementation_branch="impl/1/2-implementation-child",
            worktree_path="/worktrees/demo/issue-2",
        ),
        ClaimResult(
            issue_number=3,
            agent_run_id="run-bbb",
            implementation_branch="impl/1/3-another-child",
            worktree_path="/worktrees/demo/issue-3",
        ),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(
            issue_number=2,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
        ExecutionResult(
            issue_number=3,
            status="succeeded",
            exit_code=0,
            new_commits=True,
        ),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.side_effect = [
        IntegrationResult(issue_number=2, status="succeeded", implementation_branch="impl/1/2-implementation-child", prd_branch="prd/1-prd-1"),
        IntegrationResult(issue_number=3, status="succeeded", implementation_branch="impl/1/3-another-child", prd_branch="prd/1-prd-1"),
    ]

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    # Before run, the set is empty
    assert len(orchestrator._active_agent_run_issue_numbers) == 0

    orchestrator.run("demo", config)

    # After run completes, the active set is cleared
    assert len(orchestrator._active_agent_run_issue_numbers) == 0

    # Both issues were dispatched
    assert len(fake_executor.submitted) == 2


def test_continuous_mode_passes_active_runs_to_planner() -> None:
    """In continuous mode, in-memory active runs are passed to the planner on subsequent passes."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Another child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#2",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )

    # First plan/list: all issues present (impl_2 claimable, impl_3 blocked by #2)
    # After first pass, #2 is claimed (gets claim metadata in GitHub)
    # Second pass: #2 has claim metadata (not ready-for-agent), #3 is still blocked
    claimed_2 = GitHubIssueRecord(
        number=2,
        title="Implementation child",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone\n\n## Orchestration\n- Agent Run: run-aaa\n- Claimed At: 2026-05-29T13:00:00Z\n- Implementation Branch: impl/1/2-implementation-child",
        labels=("implementation",),
        state="open",
    )

    issues_gateway.list_issues.side_effect = PassBasedListIssuesMock([
        (prd_1, impl_2, impl_3),
        (prd_1, claimed_2, impl_3),
    ])


    fake_executor = FakeExecutor()

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        executor=fake_executor,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-aaa",
        implementation_branch="impl/1/2-implementation-child",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2,
        status="succeeded",
        exit_code=0,
        new_commits=True,
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2,
        status="succeeded",
        implementation_branch="impl/1/2-implementation-child",
        prd_branch="prd/1-prd-1",
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

    orchestrator.run("demo", config, continuous=True)

    # In the first pass, impl_2 was claimable and dispatched
    assert orchestrator.claim_service.claim_issue.call_count == 1
    # The second pass found no claimable issues (impl_2 is blocked, impl_3 still blocked)
    # Reconcile runs: orchestrator start, after drain (meaningful outcome), orchestrator end.
    assert orchestrator.reconciliation_service.reconcile.call_count == 3


class FakeDelayingExecutor:
    """Fake executor that runs tasks in separate threads (not the main thread)
to simulate real concurrent execution. Supports a barrier for synchronisation."""

    def __init__(self) -> None:
        self.submitted: list[tuple] = []
        self._threads: list[threading.Thread] = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        result_container: list = []
        exception_container: list[Exception | None] = [None]

        def wrapper():
            try:
                result_container.append(fn(*args, **kwargs))
            except Exception as exc:
                exception_container[0] = exc

        t = threading.Thread(target=wrapper, daemon=True)
        self._threads.append(t)
        t.start()

        future: Future = Future()

        def set_result_when_done():
            t.join()
            if exception_container[0] is not None:
                future.set_exception(exception_container[0])
            elif result_container:
                future.set_result(result_container[0])
            else:
                future.set_result(None)

        threading.Thread(target=set_result_when_done, daemon=True).start()
        return future

    def shutdown(self, wait: bool = True) -> None:
        pass


class BlockingIntegrationGateway:
    """A FakeIssueGateway that can block inside integrate_issue until released.
Used to test that integration is serialized and doesn't block Agent Runs."""

    def __init__(self, underlying_service: MagicMock) -> None:
        self._service = underlying_service
        self._block_event = threading.Event()
        self._release_event = threading.Event()
        self._entered_count = 0
        self._lock = threading.Lock()

    @property
    def integrate_issue(self):
        original = self._service.integrate_issue

        def blocking_integrate(*args, **kwargs):
            with self._lock:
                self._entered_count += 1
                count = self._entered_count
            self._block_event.set()  # signal that we've entered
            self._release_event.wait()  # block until released
            return original(*args, **kwargs)

        return blocking_integrate


def test_integration_is_serialized_when_multiple_agent_runs_finish_together() -> None:
    """When two Agent Runs succeed at roughly the same time,
    their integrations must execute one at a time (serialized)."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation A",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Implementation B",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it too.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2, impl_3)

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(
            issue_number=2,
            agent_run_id="run-aaa",
            implementation_branch="impl/1/2-impl-a",
            worktree_path="/worktrees/demo/issue-2",
        ),
        ClaimResult(
            issue_number=3,
            agent_run_id="run-bbb",
            implementation_branch="impl/1/3-impl-b",
            worktree_path="/worktrees/demo/issue-3",
        ),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True),
        ExecutionResult(issue_number=3, status="succeeded", exit_code=0, new_commits=True),
    ]

    # Track integration calls and their timing
    integration_start_times: list[float] = []
    integration_end_times: list[float] = []
    integration_call_lock = threading.Lock()

    real_integration = MagicMock()
    real_integration.integrate_issue.side_effect = [
        IntegrationResult(issue_number=2, status="succeeded", implementation_branch="impl/1/2-impl-a", prd_branch="prd/1-prd-1"),
        IntegrationResult(issue_number=3, status="succeeded", implementation_branch="impl/1/3-impl-b", prd_branch="prd/1-prd-1"),
    ]

    def tracking_integrate(*args, **kwargs):
        start = time.monotonic()
        with integration_call_lock:
            integration_start_times.append(start)
        time.sleep(0.1)  # Simulate some integration work
        result = real_integration.integrate_issue(*args, **kwargs)
        end = time.monotonic()
        with integration_call_lock:
            integration_end_times.append(end)
        return result

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue = tracking_integrate

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Both integrations should have been called
    assert len(integration_start_times) == 2
    assert len(integration_end_times) == 2

    # Integration calls must not overlap: the first must end before the second begins
    # Since they are serialized, start[1] >= end[0]
    assert integration_start_times[1] >= integration_end_times[0], (
        f"Integration calls overlapped: start2={integration_start_times[1]}, end1={integration_end_times[0]}"
    )


def test_later_issue_integrates_before_earlier_still_running_issue_when_no_blocking_dependency() -> None:
    """When issue #3 finishes execution before issue #2 (which is still running),
    #3 should integrate before #2 if there is no blocking dependency between them."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation (slower)",
        body="## Parent PRD\n#1\n\n## What to Build\nSlow build.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Implementation (faster)",
        body="## Parent PRD\n#1\n\n## What to Build\nFast build.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2, impl_3)

    # Use a real ThreadPoolExecutor so the two Agent Runs run concurrently.
    # Execution for issue #3 returns immediately; execution for issue #2
    # sleeps long enough that #3 finishes first, entering the integration
    # queue before #2.
    from concurrent.futures import ThreadPoolExecutor

    # Ensure #3's _run_agent_run completes (enqueues for integration)
    # before #2's _run_agent_run finishes.  We detect #3's enqueue by
    # intercepting the agent_run.finished event.
    fast_done = threading.Event()
    slow_started = threading.Event()
    issue_3_enqueued = threading.Event()

    def event_catcher(event: SchedulerEvent) -> None:
        if event.event == "agent_run.finished" and event.issue_number == 3:
            issue_3_enqueued.set()

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
        executor=ThreadPoolExecutor(max_workers=2),
        event_emitter=event_catcher,
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(issue_number=2, agent_run_id="run-aaa", implementation_branch="impl/1/2-slower", worktree_path="/worktrees/demo/issue-2"),
        ClaimResult(issue_number=3, agent_run_id="run-bbb", implementation_branch="impl/1/3-faster", worktree_path="/worktrees/demo/issue-3"),
    ]

    def execute_run_side_effect(*, repo_name, issue_number, config):
        if issue_number == 2:
            slow_started.set()
            fast_done.wait()       # Wait until #3 finishes execution
            issue_3_enqueued.wait()  # Wait until #3's queue item is enqueued
            return ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True)
        else:
            time.sleep(0.05)       # Small delay so #2's thread has time to start
            fast_done.set()        # Signal that #3's execution is done
            return ExecutionResult(issue_number=3, status="succeeded", exit_code=0, new_commits=True)

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = execute_run_side_effect

    # Record integration order
    integration_order: list[int] = []
    integration_lock = threading.Lock()

    def integrate_side_effect(*, repo_path, worktree_root, issue_number):
        with integration_lock:
            integration_order.append(issue_number)
        return IntegrationResult(issue_number=issue_number, status="succeeded")

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.side_effect = integrate_side_effect

    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=Path("/repos/demo"),
            main_branch="main",
            worktree_root=Path("/worktrees/demo"),
            global_concurrency=2,
            per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Both integrations should have been called
    assert orchestrator.integration_service.integrate_issue.call_count == 2

    # Issue #3 must integrate before issue #2 because it finished execution first
    # and entered the integration queue first (no blocking dependencies).
    assert integration_order == [3, 2], (
        f"Expected integration order [3, 2] (later-issue first since it finished"
        f" execution earlier), got {integration_order}"
    )


def test_agent_run_capacity_freed_after_execution_not_after_integration() -> None:
    """Agent Run Capacity must be freed when execution completes, not when integration completes.
    The active set is cleared after Agent Runs finish, even though integration may still be in progress."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2)

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-aaa",
        implementation_branch="impl/1/2-impl",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2, status="succeeded", exit_code=0, new_commits=True,
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

    # Before run, active set is empty
    assert len(orchestrator._active_agent_run_issue_numbers) == 0

    orchestrator.run("demo", config)

    # After run returns, active set should be empty (capacity freed after execution)
    # even though integration happens in the background
    assert len(orchestrator._active_agent_run_issue_numbers) == 0


def test_integration_failure_leaves_issue_for_human_review_in_orchestrator_context() -> None:
    """When integration fails, the issue should get needs-triage label and not be retried.
    The orchestrator should NOT attempt integration again for the same issue."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD 1",
        body="## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/1-prd-1",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Implementation",
        body="## Parent PRD\n#1\n\n## What to Build\nBuild it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    issues_gateway.list_issues.return_value = (prd_1, impl_2)

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=2,
        agent_run_id="run-aaa",
        implementation_branch="impl/1/2-impl",
        worktree_path="/worktrees/demo/issue-2",
    )

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=2, status="succeeded", exit_code=0, new_commits=True,
    )

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=2,
        status="failed",
        failure_type="merge_conflict",
        failure_message="CONFLICT in some-file.txt",
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

    # Integration was attempted exactly once (no retry)
    assert orchestrator.integration_service.integrate_issue.call_count == 1

    # Integration was called with the correct issue
    orchestrator.integration_service.integrate_issue.assert_called_once_with(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=2,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Issue #40: Continuous drain scheduling for dependency waves
# ──────────────────────────────────────────────────────────────────────────────


def test_continuous_mode_drains_dependency_waves() -> None:
    """When an issue integrates and closes, a previously-blocked dependent
    issue should become claimable and get dispatched in the *same* continuous
    orchestrator invocation."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Impl A (blocker)",
        body="## Parent PRD\n#1\n\n## What to Build\nA.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl B (blocked by A)",
        body="## Parent PRD\n#1\n\n## What to Build\nB.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#2",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )

    # After #2 integrates successfully, it becomes closed.
    impl_2_closed = GitHubIssueRecord(
        number=2,
        title="Impl A (blocker)",
        body=impl_2.body,
        labels=("implementation",),
        state="closed",
    )
    # After #3 is dispatched and integrated, it becomes closed.
    impl_3_closed = GitHubIssueRecord(
        number=3,
        title="Impl B (blocked by A)",
        body=impl_3.body,
        labels=("implementation",),
        state="closed",
    )

    issues_gateway.list_issues.side_effect = PassBasedListIssuesMock([
        (prd_1, impl_2, impl_3),
        (prd_1, impl_2_closed, impl_3),
        (prd_1, impl_2_closed, impl_3_closed),
    ])


    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(issue_number=2, agent_run_id="run-aaa", implementation_branch="impl/1/2-impl-a", worktree_path="/worktrees/demo/issue-2"),
        ClaimResult(issue_number=3, agent_run_id="run-bbb", implementation_branch="impl/1/3-impl-b", worktree_path="/worktrees/demo/issue-3"),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True),
        ExecutionResult(issue_number=3, status="succeeded", exit_code=0, new_commits=True),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.side_effect = [
        IntegrationResult(issue_number=2, status="succeeded", implementation_branch="impl/1/2-impl-a", prd_branch="prd/1-prd"),
        IntegrationResult(issue_number=3, status="succeeded", implementation_branch="impl/1/3-impl-b", prd_branch="prd/1-prd"),
    ]

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2, per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config, continuous=True)

    # Both issues should have been dispatched across scheduling passes
    assert orchestrator.claim_service.claim_issue.call_count == 2
    assert orchestrator.execution_service.execute_run.call_count == 2
    assert orchestrator.integration_service.integrate_issue.call_count == 2

    # Integration calls happen in order: #2 first (dispatched first), #3 second
    integrate_calls = orchestrator.integration_service.integrate_issue.call_args_list
    assert integrate_calls[0].kwargs["issue_number"] == 2
    assert integrate_calls[1].kwargs["issue_number"] == 3


def test_continuous_mode_stops_when_truly_idle() -> None:
    """Continuous mode stops when no claimable issues, no active Agent Runs,
    and no pending integrations remain."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    # No ready-for-agent implementation issues
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Impl (not ready)",
        body="## Parent PRD\n#1\n\n## What to Build\nA.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation",),  # no ready-for-agent
        state="open",
    )

    # prepare_prds + plan_actions (2 calls per plan: open + closed)
    issues_gateway.list_issues.side_effect = [
        (prd_1, impl_2),          # prepare_prds
        (prd_1, impl_2),          # plan pass 1: open
        (prd_1, impl_2),          # plan pass 1: closed
    ]

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.execution_service = MagicMock()
    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2, per_prd_concurrency=1,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config, continuous=True)

    # Nothing claimable → nothing dispatched
    orchestrator.claim_service.claim_issue.assert_not_called()
    orchestrator.execution_service.execute_run.assert_not_called()
    orchestrator.integration_service.integrate_issue.assert_not_called()


def test_continuous_mode_does_not_exit_early_while_integrations_pending() -> None:
    """Continuous mode must not exit while integrations are still pending,
    because those integrations may unblock currently-blocked Ready Issues.
    
    Simulates: #2 was dispatched and succeeded in a prior pass, but its
    integration hasn't completed yet.  #3 is blocked by #2.  The loop must
    drain the pending integration, find #2 closed, and then claim #3."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    impl_2 = GitHubIssueRecord(
        number=2,
        title="Impl A",
        body="## Parent PRD\n#1\n\n## What to Build\nA.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl B (blocked by A)",
        body="## Parent PRD\n#1\n\n## What to Build\nB.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#2",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )

    # After integration closes #2, #3 becomes unblocked
    impl_2_closed = GitHubIssueRecord(
        number=2,
        title="Impl A",
        body=impl_2.body,
        labels=("implementation",),
        state="closed",
    )
    # After #3 is dispatched and integrated, it becomes closed.
    impl_3_closed = GitHubIssueRecord(
        number=3,
        title="Impl B (blocked by A)",
        body=impl_3.body,
        labels=("implementation",),
        state="closed",
    )

    # plan_actions now fetches open + closed separately (2 calls per pass)
    issues_gateway.list_issues.side_effect = [
        (prd_1, impl_2, impl_3),          # prepare_prds
        (prd_1, impl_2, impl_3),          # plan pass 1: open
        (prd_1, impl_2, impl_3),          # plan pass 1: closed
        (prd_1, impl_2_closed, impl_3),   # plan pass 2: open
        (prd_1, impl_2_closed, impl_3),   # plan pass 2: closed
        (prd_1, impl_2_closed, impl_3_closed),  # plan pass 3: open
        (prd_1, impl_2_closed, impl_3_closed),  # plan pass 3: closed
    ]

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()

    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.side_effect = [
        ClaimResult(issue_number=2, agent_run_id="run-aaa", implementation_branch="impl/1/2-impl-a", worktree_path="/worktrees/demo/issue-2"),
        ClaimResult(issue_number=3, agent_run_id="run-bbb", implementation_branch="impl/1/3-impl-b", worktree_path="/worktrees/demo/issue-3"),
    ]

    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.side_effect = [
        ExecutionResult(issue_number=2, status="succeeded", exit_code=0, new_commits=True),
        ExecutionResult(issue_number=3, status="succeeded", exit_code=0, new_commits=True),
    ]

    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.side_effect = [
        IntegrationResult(issue_number=2, status="succeeded", implementation_branch="impl/1/2-impl-a", prd_branch="prd/1-prd"),
        IntegrationResult(issue_number=3, status="succeeded", implementation_branch="impl/1/3-impl-b", prd_branch="prd/1-prd"),
    ]

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2, per_prd_concurrency=2,
            default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config, continuous=True)

    # The loop must NOT exit early — it must drain integration, re-plan,
    # find #3 now unblocked, and dispatch it.
    assert orchestrator.claim_service.claim_issue.call_count == 2
    assert orchestrator.execution_service.execute_run.call_count == 2
    assert orchestrator.integration_service.integrate_issue.call_count == 2

    # Verify #3 was dispatched (not lost to premature exit)
    claim_numbers = [
        call.kwargs["issue_number"]
        for call in orchestrator.claim_service.claim_issue.call_args_list
    ]
    assert claim_numbers == [2, 3], f"Expected claims for [2, 3], got {claim_numbers}"


# ── Issue #52: Sliding time-window fallback tests ────────────────────────────


def test_plan_actions_resolves_missing_blocker_via_view_issue_when_closed() -> None:
    """When an implementation issue is blocked by another issue that falls
    outside the 24h sliding window cache, the orchestrator resolves it via
    view_issue(). If the blocker is closed, the issue is unblocked."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl blocked by old-closed #2",
        body="## Parent PRD\n#1\n\n## What to Build\nDo it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#2",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    # #2 is NOT in list_issues (simulating it fell out of the 24h cache)
    issues_gateway.list_issues.return_value = (prd_1, impl_3)

    # view_issue resolves #2 as a closed implementation issue
    impl_2_closed = GitHubIssueRecord(
        number=2,
        title="Old closed blocker",
        body="## Parent PRD\n#1\n\n## What to Build\nOld.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation",),
        state="closed",
    )
    issues_gateway.view_issue.return_value = impl_2_closed

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.claim_service.claim_issue.return_value = ClaimResult(
        issue_number=3, agent_run_id="run-ccc",
        implementation_branch="impl/1/3-impl", worktree_path="/worktrees/demo/issue-3",
    )
    orchestrator.execution_service = MagicMock()
    orchestrator.execution_service.execute_run.return_value = ExecutionResult(
        issue_number=3, status="succeeded", exit_code=0, new_commits=True,
    )
    orchestrator.integration_service = MagicMock()
    orchestrator.integration_service.integrate_issue.return_value = IntegrationResult(
        issue_number=3, status="succeeded",
        implementation_branch="impl/1/3-impl", prd_branch="prd/1-prd",
    )

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2,
            per_prd_concurrency=2, default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # view_issue should have been called for the missing blocker #2
    issues_gateway.view_issue.assert_called_once_with(2)
    # #3 should have been claimed (unblocked since #2 is closed)
    orchestrator.claim_service.claim_issue.assert_called_once()
    assert orchestrator.claim_service.claim_issue.call_args.kwargs["issue_number"] == 3


def test_plan_actions_resolves_missing_blocker_via_view_issue_when_open() -> None:
    """When a missing blocker is resolved via view_issue() and is still open,
    the dependent issue remains blocked and is not claimed."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl blocked by old-open #2",
        body="## Parent PRD\n#1\n\n## What to Build\nDo it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#2",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    # #2 is NOT in list_issues
    issues_gateway.list_issues.return_value = (prd_1, impl_3)

    # view_issue resolves #2 as an open implementation issue
    impl_2_open = GitHubIssueRecord(
        number=2,
        title="Old open blocker",
        body="## Parent PRD\n#1\n\n## What to Build\nOld.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\nNone",
        labels=("implementation",),
        state="open",
    )
    issues_gateway.view_issue.return_value = impl_2_open

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.execution_service = MagicMock()
    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2,
            per_prd_concurrency=2, default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # view_issue should have been called for the missing blocker #2
    issues_gateway.view_issue.assert_called_once_with(2)
    # #3 should NOT have been claimed (still blocked since #2 is open)
    orchestrator.claim_service.claim_issue.assert_not_called()


def test_plan_actions_view_issue_failure_still_produces_diagnostic() -> None:
    """When view_issue() fails for a missing blocker (e.g. deleted issue),
    the planner still produces a diagnostic rather than crashing."""
    issues_gateway = MagicMock()

    prd_1 = GitHubIssueRecord(
        number=1,
        title="PRD",
        body="## Problem Statement\n\nPlan.\n\n## Orchestration\n- PRD Branch: prd/1-prd",
        labels=("prd",),
        state="open",
    )
    impl_3 = GitHubIssueRecord(
        number=3,
        title="Impl blocked by deleted #99",
        body="## Parent PRD\n#1\n\n## What to Build\nDo it.\n\n## Acceptance Criteria\n- [ ] Done.\n\n## Blocked By\n#99",
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    # #99 is NOT in list_issues
    issues_gateway.list_issues.return_value = (prd_1, impl_3)
    # view_issue fails for #99
    issues_gateway.view_issue.side_effect = RuntimeError("Issue not found")

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.execution_service = MagicMock()
    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2,
            per_prd_concurrency=2, default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    # Should not crash
    orchestrator.run("demo", config)

    # view_issue was attempted for the missing blocker
    issues_gateway.view_issue.assert_called_once_with(99)
    # #3 should NOT be claimed (blocker unresolvable → needs-triage diagnostic)
    orchestrator.claim_service.claim_issue.assert_not_called()


def test_plan_actions_with_sliding_window_passes_labels_and_updated_since() -> None:
    """The orchestrator fetches open issues without a time window
    and closed issues with a 24h updated_since for the planning pass."""
    issues_gateway = MagicMock()
    issues_gateway.list_issues.return_value = ()

    orchestrator = Orchestrator(
        issues_gateway=issues_gateway,
        now_provider=lambda: "2026-05-29T17:00:00Z",
    )
    orchestrator.reconciliation_service = MagicMock()
    orchestrator.prd_preparation_service = MagicMock()
    orchestrator.claim_service = MagicMock()
    orchestrator.execution_service = MagicMock()
    orchestrator.integration_service = MagicMock()

    repos = {
        "demo": RepoConfig(
            name="demo", repo_path=Path("/repos/demo"), main_branch="main",
            worktree_root=Path("/worktrees/demo"), global_concurrency=2,
            per_prd_concurrency=2, default_harness="local",
        )
    }
    config = AppConfig(repos=repos, harnesses={})

    orchestrator.run("demo", config)

    # Verify the open-issue fetch (from plan_actions, not prepare_prds)
    # has labels=(prd, implementation) but no updated_since
    open_calls = [
        call for call in issues_gateway.list_issues.call_args_list
        if call.kwargs.get("state") == "open"
        and call.kwargs.get("labels") == ("prd", "implementation")
    ]
    assert len(open_calls) >= 1
    open_call = open_calls[0]
    assert open_call.kwargs["labels"] == ("prd", "implementation")
    assert open_call.kwargs.get("updated_since") is None

    # Verify the closed-issue fetch has labels AND updated_since
    closed_calls = [
        call for call in issues_gateway.list_issues.call_args_list
        if call.kwargs.get("state") == "closed"
    ]
    assert len(closed_calls) >= 1
    closed_call = closed_calls[0]
    assert closed_call.kwargs["labels"] == ("prd", "implementation")
    assert closed_call.kwargs["updated_since"] == "2026-05-28"

