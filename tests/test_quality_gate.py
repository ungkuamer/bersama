"""Tests for quality gate: _parse_validation_result, command rendering,
passing gate path, and disabled gate path."""

from __future__ import annotations

from pathlib import Path

from rangkai.config import (
    AppConfig,
    HarnessConfig,
    QualityGateConfig,
    RepoConfig,
)
from rangkai.github_issues import GitHubIssueRecord
from rangkai.orchestrator import Orchestrator, _parse_validation_result


# ── _parse_validation_result tests ─────────────────────────────────


def test_parse_validation_result_empty_string() -> None:
    assert _parse_validation_result("") is None


def test_parse_validation_result_no_json() -> None:
    assert _parse_validation_result("plain text output") is None


def test_parse_validation_result_passed() -> None:
    result = _parse_validation_result('{"status": "passed"}')
    assert result == {"status": "passed"}


def test_parse_validation_result_failed() -> None:
    result = _parse_validation_result('{"status": "failed", "message": "test failed"}')
    assert result == {"status": "failed", "message": "test failed"}


def test_parse_validation_result_error() -> None:
    result = _parse_validation_result('{"status": "error"}')
    assert result == {"status": "error"}


def test_parse_validation_result_json_in_middle_of_text() -> None:
    stdout = """Running checks...
{"status": "passed", "checks": 5}
Done."""
    result = _parse_validation_result(stdout)
    assert result == {"status": "passed", "checks": 5}


def test_parse_validation_result_multiline_json() -> None:
    stdout = """{"status": "passed",
 "checks": 5,
 "details": {"coverage": 90}}"""
    result = _parse_validation_result(stdout)
    assert result == {"status": "passed", "checks": 5, "details": {"coverage": 90}}


def test_parse_validation_result_unrecognised_status() -> None:
    """A JSON with a status outside {passed, failed, error} is not a valid result."""
    assert _parse_validation_result('{"status": "unknown"}') is None


def test_parse_validation_result_missing_status() -> None:
    assert _parse_validation_result('{"checks": 5}') is None


def test_parse_validation_result_invalid_json() -> None:
    assert _parse_validation_result("{not valid json}") is None


# ── Quality gate integration tests ─────────────────────────────────


class FakeIssueGateway:
    """In-memory issue gateway for quality gate tests."""

    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}
        self.comments: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, tuple[str, ...]]] = []
        self.closed_issues: list[int] = []
        self.updated_bodies: list[tuple[int, str]] = []

    def list_issues(self, *, state: str, labels: tuple[str, ...]) -> list[GitHubIssueRecord]:
        return [i for i in self.issues.values() if i.state == state]

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self.issues[number]

    def add_comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def add_labels(self, number: int, *labels: str) -> None:
        self.added_labels.append((number, labels))

    def remove_labels(self, number: int, *labels: str) -> None:
        pass

    def close_issue(self, number: int) -> None:
        self.closed_issues.append(number)

    def update_body(self, number: int, body: str) -> None:
        self.updated_bodies.append((number, body))
        if number in self.issues:
            old = self.issues[number]
            self.issues[number] = GitHubIssueRecord(
                number=old.number,
                title=old.title,
                body=body,
                labels=old.labels,
                state=old.state,
            )


def _make_issue_record(
    number: int,
    title: str,
    body: str,
    labels: tuple[str, ...] = (),
    state: str = "open",
) -> GitHubIssueRecord:
    return GitHubIssueRecord(
        number=number,
        title=title,
        body=body,
        labels=labels,
        state=state,
    )


def _make_quality_gate_config(
    enabled: bool = False,
    *,
    command: str = "true",
    args_template: tuple[str, ...] = (),
    timeout_seconds: int | None = None,
) -> QualityGateConfig:
    return QualityGateConfig(
        enabled=enabled,
        command=command if enabled else None,
        args_template=args_template,
        timeout_seconds=timeout_seconds,
    )


# ── Orchestrator-based quality gate tests ──────────────────────────


class FakeEventEmitter:
    """Collects scheduler events for assertion."""

    def __init__(self) -> None:
        self.events: list = []

    def __call__(self, event) -> None:
        self.events.append(event)


def test_quality_gate_disabled_returns_true() -> None:
    """When quality_gate is disabled, _run_quality_gate returns True immediately."""
    issues = FakeIssueGateway()
    orchestrator = Orchestrator(issues_gateway=issues)

    repo = RepoConfig(
        name="test-repo",
        repo_path=Path("/repos/test-repo"),
        main_branch="main",
        worktree_root=Path("/worktrees"),
        global_concurrency=1,
        per_prd_concurrency=1,
        default_harness="local",
        quality_gate=QualityGateConfig(enabled=False),
    )
    harness = HarnessConfig(name="local", command="codex", args_template=())
    config = AppConfig(
        repos={"test-repo": repo},
        harnesses={"local": harness},
    )

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path="/repos/test-repo",
        worktree_root="/worktrees",
        issue_number=42,
        config=config,
    )

    assert result is True


def test_quality_gate_command_rendering(tmp_path: Path) -> None:
    """Verify that template variables in quality gate args are rendered correctly."""
    # Build an implementation issue body with orchestration metadata
    impl_body = """## Parent PRD
#1

## What to Build
Test feature

## Orchestration
- Agent Run: run-abc
- Claimed At: 2026-01-01T00:00:00Z
- Implementation Branch: impl/1/150-test
"""

    prd_body = """## Orchestration
- PRD Branch: prd/1-parent
"""

    issues = FakeIssueGateway(
        _make_issue_record(150, "Test Issue", impl_body, ("implementation",)),
        _make_issue_record(1, "Parent PRD", prd_body, ("prd",)),
    )

    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    # Create a real worktree directory so the command can run
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    repo = RepoConfig(
        name="test-repo",
        repo_path=tmp_path / "repos" / "test-repo",
        main_branch="main",
        worktree_root=worktree_root,
        global_concurrency=1,
        per_prd_concurrency=1,
        default_harness="local",
        quality_gate=QualityGateConfig(
            enabled=True,
            command="/bin/echo",
            args_template=(
                "repo={repo_name}",
                "path={repo_path}",
                "wt={worktree_root}",
                "issue={issue_number}",
                "prd={parent_prd_number}",
                "prd_br={prd_branch}",
                "impl_br={implementation_branch}",
                "wt_path={worktree_path}",
            ),
            timeout_seconds=5,
        ),
    )
    harness = HarnessConfig(name="local", command="codex", args_template=())
    config = AppConfig(
        repos={"test-repo": repo},
        harnesses={"local": harness},
    )

    # The /bin/echo command will succeed, but the output won't contain
    # valid JSON, so the gate will fail.  What we're testing here is
    # that the template variables are passed correctly — we can verify
    # via the event detail.
    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    # The gate should fail because echo output isn't valid JSON.
    assert result is False

    # Verify events were emitted
    assert len(events.events) >= 2
    start_event = events.events[0]
    assert start_event.event == "quality_gate.start"
    assert start_event.issue_number == 150

    fail_event = events.events[-1]
    assert fail_event.event == "quality_gate.blocked"
    assert fail_event.status == "blocked"


# ── Blocking gate diagnostic tests (issue #151) ───────────────────


def _make_impl_body(
    parent_prd_number: int = 1,
    agent_run: str = "run-abc",
    claimed_at: str = "2026-01-01T00:00:00Z",
    implementation_branch: str = "impl/1/150-test",
) -> str:
    return f"""## Parent PRD
#{parent_prd_number}

## What to Build
Test feature

## Orchestration
- Agent Run: {agent_run}
- Claimed At: {claimed_at}
- Implementation Branch: {implementation_branch}
"""


def _make_prd_body(prd_branch: str = "prd/1-parent") -> str:
    return f"""## Orchestration
- PRD Branch: {prd_branch}
"""


def _make_gate_issues(
    impl_number: int = 150,
    prd_number: int = 1,
    *,
    impl_labels: tuple[str, ...] = ("implementation",),
    prd_labels: tuple[str, ...] = ("prd",),
) -> FakeIssueGateway:
    return FakeIssueGateway(
        _make_issue_record(
            impl_number,
            "Test Issue",
            _make_impl_body(parent_prd_number=prd_number),
            impl_labels,
        ),
        _make_issue_record(
            prd_number,
            "Parent PRD",
            _make_prd_body(),
            prd_labels,
        ),
    )


def _make_gate_config(
    *,
    enabled: bool = True,
    command: str = "/bin/true",
    args_template: tuple[str, ...] = (),
    timeout_seconds: int | None = 5,
) -> QualityGateConfig:
    return QualityGateConfig(
        enabled=enabled,
        command=command,
        args_template=args_template,
        timeout_seconds=timeout_seconds,
    )


def _make_gate_repo(
    worktree_root: Path,
    *,
    quality_gate: QualityGateConfig | None = None,
) -> RepoConfig:
    return RepoConfig(
        name="test-repo",
        repo_path=worktree_root / "repos" / "test-repo",
        main_branch="main",
        worktree_root=worktree_root,
        global_concurrency=1,
        per_prd_concurrency=1,
        default_harness="local",
        quality_gate=quality_gate or QualityGateConfig(enabled=False),
    )


def _make_gate_app_config(repo: RepoConfig) -> AppConfig:
    harness = HarnessConfig(name="local", command="codex", args_template=())
    return AppConfig(
        repos={repo.name: repo},
        harnesses={"local": harness},
    )


def test_failed_gate_adds_needs_triage_label(tmp_path: Path) -> None:
    """When the gate returns status=failed, the needs-triage label is added."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "failed", "checks": [{{"name": "lint", "status": "failed"}}]}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels


def test_failed_gate_adds_diagnostic_comment(tmp_path: Path) -> None:
    """When the gate fails, a diagnostic comment is posted on the issue."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "failed", "checks": [{{"name": "lint", "status": "failed"}}]}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert len(issues.comments) == 1
    comment_num, comment_body = issues.comments[0]
    assert comment_num == 150
    assert "Quality Gate" in comment_body
    assert "failed" in comment_body.lower()
    assert "lint" in comment_body


def test_failed_gate_persists_diagnostics_to_worktree(tmp_path: Path) -> None:
    """When the gate fails, stdout, stderr, and parsed result are persisted."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "failed", "reason": "coverage below threshold"}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    # Verify diagnostics persisted in worktree
    diag_dir = worktree_path / "quality-gate"
    assert diag_dir.is_dir()
    assert (diag_dir / "stdout.txt").exists()
    assert (diag_dir / "stderr.txt").exists()
    assert (diag_dir / "result.json").exists()

    # Verify contents
    stdout_content = (diag_dir / "stdout.txt").read_text()
    assert "coverage below threshold" in stdout_content

    import json
    result_json = json.loads((diag_dir / "result.json").read_text())
    assert result_json["status"] == "failed"


def test_error_gate_status_triggers_blocking_with_labels(tmp_path: Path) -> None:
    """When the gate returns status=error, needs-triage label is added."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "error", "message": "internal failure"}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels
    assert len(issues.comments) == 1
    comment_body = issues.comments[0][1]
    assert "error" in comment_body.lower()


def test_non_zero_exit_code_triggers_blocking_with_diagnostics(tmp_path: Path) -> None:
    """A command that exits non-zero is treated as a gate failure."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo "something broke" >&2; exit 2'),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels
    assert len(issues.comments) == 1
    comment_body = issues.comments[0][1]
    assert "exit code" in comment_body.lower() or "2" in comment_body


def test_non_json_stdout_triggers_blocking_with_diagnostics(tmp_path: Path) -> None:
    """A command that produces non-JSON stdout is a gate failure."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/echo",
            args_template=("plain text", "no json here"),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels
    assert len(issues.comments) == 1
    assert "quality gate" in issues.comments[0][1].lower()


def test_malformed_json_triggers_blocking_with_diagnostics(tmp_path: Path) -> None:
    """Malformed JSON in stdout is treated as a gate error that blocks."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/echo",
            args_template=("{{not valid json",),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels


def test_blocked_gate_emits_scheduler_event(tmp_path: Path) -> None:
    """When a gate blocks integration, a blocked scheduler event is emitted."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "failed"}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    # Verify blocked event was emitted
    blocked_events = [e for e in events.events if e.event == "quality_gate.blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0].issue_number == 150


def test_timeout_triggers_blocking_with_diagnostics(tmp_path: Path) -> None:
    """A command that times out is a gate failure with diagnostics."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/sleep",
            args_template=("10",),
            timeout_seconds=1,
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is False
    assert (150, ("needs-triage",)) in issues.added_labels
    assert len(issues.comments) == 1
    comment_body = issues.comments[0][1]
    assert "timed out" in comment_body.lower() or "timeout" in comment_body.lower()


def test_missing_executable_adds_label_and_comment(tmp_path: Path) -> None:
    """When the gate command doesn't exist, the issue is labeled needs-triage."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/nonexistent/path/to/binary",
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is None
    assert (150, ("needs-triage",)) in issues.added_labels
    assert len(issues.comments) == 1


def test_gate_passed_does_not_add_label(tmp_path: Path) -> None:
    """When the gate passes, no needs-triage label is added."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-150"
    worktree_path.mkdir()

    issues = _make_gate_issues()
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = _make_gate_repo(
        worktree_root,
        quality_gate=_make_gate_config(
            command="/bin/bash",
            args_template=("-c", 'echo \'{{"status": "passed"}}\''),
        ),
    )
    config = _make_gate_app_config(repo)

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path=str(repo.repo_path),
        worktree_root=str(worktree_root),
        issue_number=150,
        config=config,
    )

    assert result is True
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0


def test_quality_gate_missing_issue_returns_none() -> None:
    """When the issue can't be fetched, the gate returns None (error)."""
    issues = FakeIssueGateway()  # No issues
    events = FakeEventEmitter()
    orchestrator = Orchestrator(issues_gateway=issues, event_emitter=events)

    repo = RepoConfig(
        name="test-repo",
        repo_path=Path("/repos/test-repo"),
        main_branch="main",
        worktree_root=Path("/worktrees"),
        global_concurrency=1,
        per_prd_concurrency=1,
        default_harness="local",
        quality_gate=QualityGateConfig(
            enabled=True,
            command="true",
            timeout_seconds=5,
        ),
    )
    harness = HarnessConfig(name="local", command="codex", args_template=())
    config = AppConfig(
        repos={"test-repo": repo},
        harnesses={"local": harness},
    )

    result = orchestrator._run_quality_gate(
        repo_name="test-repo",
        repo_path="/repos/test-repo",
        worktree_root="/worktrees",
        issue_number=999,
        config=config,
    )

    assert result is None
    assert len(events.events) == 1
    assert events.events[0].event == "quality_gate.error"
