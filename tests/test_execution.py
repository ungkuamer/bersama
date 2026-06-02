from __future__ import annotations

import json
from pathlib import Path
import subprocess

from unittest.mock import MagicMock

from bersama.config import AppConfig, HarnessConfig, ObservabilityConfig, RepoConfig
from bersama.execution import HarnessExecutionService
from bersama.github_issues import GitHubIssueRecord


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self.issues[number]

    def add_comment(self, number: int, body: str) -> None:
        pass

    def add_labels(self, number: int, *labels: str) -> None:
        pass

    def remove_labels(self, number: int, *labels: str) -> None:
        pass


def setup_test_git_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Helper to initialize repository and checkout worktree. Returns (repo_path, worktree_root, worktree_path)."""
    # 1. Initialize main repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True)

    dummy = repo_path / "dummy.txt"
    dummy.write_text("initial")
    subprocess.run(["git", "add", "dummy.txt"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_path, check=True, capture_output=True)

    # Create prd branch
    prd_branch = "prd/1-parent-prd"
    subprocess.run(["git", "checkout", "-b", prd_branch], cwd=repo_path, check=True, capture_output=True)

    # Create implementation branch
    impl_branch = "impl/1/8-child-impl"
    subprocess.run(["git", "checkout", "-b", impl_branch], cwd=repo_path, check=True, capture_output=True)

    # Checkout main branch so that impl_branch can be checked out by worktree
    subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True, capture_output=True)

    # Set up worktree root and worktree
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), impl_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Set up Git config inside worktree so commits succeed there as well
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree_path, check=True, capture_output=True)

    return repo_path, worktree_root, worktree_path


def get_mock_issues() -> FakeIssueGateway:
    impl_issue_record = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body="""
## Parent PRD
#1

## What to Build
Run the harness.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-123
- Claimed At: 2026-05-29T16:00:00Z
- Implementation Branch: impl/1/8-child-impl
""".strip(),
        labels=("implementation",),
        state="open",
    )

    parent_prd_record = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="""
## Problem Statement
Parent PRD.

## Orchestration
- PRD Branch: prd/1-parent-prd
""".strip(),
        labels=("prd",),
        state="open",
    )

    return FakeIssueGateway(impl_issue_record, parent_prd_record)


def test_successful_execution(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    # Create AppConfig
    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "echo 'success' > result.txt && git add result.txt && git commit -m 'harness commit'"),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert result.new_commits is True
    assert result.failure_reason is None

    # Check Log File
    log_file = worktree_path / "harness.log"
    assert log_file.exists()

    # Check Run State JSON
    state_file = worktree_path / "run-state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["status"] == "succeeded"
    assert state["issue_number"] == 8
    assert state["prd_branch"] == "prd/1-parent-prd"
    assert state["implementation_branch"] == "impl/1/8-child-impl"
    assert "started_at" in state
    assert "finished_at" in state


def test_execution_failure_by_non_zero_exit(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "exit 42"),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "failed"
    assert result.exit_code == 42
    assert result.new_commits is False
    assert "non-zero exit code 42" in result.failure_reason

    # Check Run State JSON
    state_file = worktree_path / "run-state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["status"] == "failed"
    assert "non-zero exit code 42" in state["failure_reason"]


def test_execution_failure_by_no_commits(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "echo 'nothing committed'"),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "failed"
    assert result.exit_code == 0
    assert result.new_commits is False
    assert "created no new commits" in result.failure_reason

    # Check Run State JSON
    state_file = worktree_path / "run-state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["status"] == "failed"
    assert "created no new commits" in state["failure_reason"]


def test_execution_timeout_kills_process_group(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    # Harness that sleeps indefinitely (hanging)
    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "sleep 999"),
            timeout_seconds=2,
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "failed"
    assert "timed out" in result.failure_reason.lower()
    assert result.exit_code != 0
    assert result.new_commits is False

    # Check Run State JSON
    state_file = worktree_path / "run-state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["status"] == "failed"
    assert "timed out" in state["failure_reason"].lower()


def test_observability_telemetry_association_metadata(tmp_path: Path) -> None:
    """When observability is enabled, run_state.json includes telemetry_association
    and the harness receives BERSAMA_TELEMETRY_ASSOCIATION in its environment."""
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=(
                "-c",
                "echo $BERSAMA_TELEMETRY_ASSOCIATION > telemetry.txt && git add telemetry.txt && git commit -m 'telemetry check'",
            ),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    observability_config = ObservabilityConfig(enabled=True, session_prefix="bersama")
    config = AppConfig(repos=repos, harnesses=harnesses, observability=observability_config)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "succeeded"

    # Verify run_state.json includes telemetry_association
    state_file = worktree_path / "run-state.json"
    state = json.loads(state_file.read_text())
    assert "telemetry_association" in state
    ta = state["telemetry_association"]
    assert ta["repo"] == "demo"
    assert ta["parent_prd"] == 1
    assert ta["issue"] == 8
    assert ta["run_id"] == "run-123"

    # Verify telemetry env var was delivered to the harness
    telemetry_file = worktree_path / "telemetry.txt"
    assert telemetry_file.exists()
    telemetry_json = json.loads(telemetry_file.read_text().strip())
    assert telemetry_json["repo"] == "demo"
    assert telemetry_json["parent_prd"] == 1
    assert telemetry_json["issue"] == 8
    assert telemetry_json["run_id"] == "run-123"


def test_observability_disabled_no_telemetry_metadata(tmp_path: Path) -> None:
    """When observability is disabled (default), no telemetry_association is written
    and BERSAMA_TELEMETRY_ASSOCIATION is not set in the harness environment."""
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=(
                "-c",
                "echo ${{BERSAMA_TELEMETRY_ASSOCIATION:-UNSET}} > telemetry_status.txt && git add telemetry_status.txt && git commit -m 'no telemetry'",
            ),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    # No observability config — defaults to disabled
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "succeeded"

    # Verify run_state.json does NOT include telemetry_association
    state_file = worktree_path / "run-state.json"
    state = json.loads(state_file.read_text())
    assert "telemetry_association" not in state

    # Verify telemetry env var was NOT set
    telemetry_file = worktree_path / "telemetry_status.txt"
    assert telemetry_file.exists()
    assert telemetry_file.read_text().strip() == "UNSET"


class FakeDiscordNotifier:
    """Records calls to send() for test verification."""
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send(self, **kwargs: object) -> None:
        self.calls.append(dict(kwargs))


def test_discord_notification_run_failed(tmp_path: Path) -> None:
    """When a run fails, the Discord notifier posts a 'Run Failed / Needs Attention' embed."""
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "exit 42"),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    fake_notifier = FakeDiscordNotifier()
    service = HarnessExecutionService(issues=issues, discord_notifier=fake_notifier)
    service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    # Should have "started" notification
    started_calls = [c for c in fake_notifier.calls if "Run Started" in str(c.get("title", ""))]
    assert len(started_calls) >= 1

    # Should have "Run Failed / Needs Attention" notification
    failed_calls = [c for c in fake_notifier.calls if "Run Failed" in str(c.get("title", ""))]
    assert len(failed_calls) >= 1, f"Expected a 'Run Failed' call, got: {fake_notifier.calls}"

    failed = failed_calls[0]
    assert failed["title"] == "Run Failed / Needs Attention"
    assert "#8" in failed["description"]
    assert "demo" in failed.get("description", "")
    assert "run-123" in failed.get("description", "")
    assert "non-zero exit code 42" in failed["description"]
    # Red/orange color for failures
    assert failed["color"] == 0xED4245


def test_discord_notification_run_started(tmp_path: Path) -> None:
    """When Discord is enabled, starting a run posts a 'Run Started' embed."""
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=("-c", "echo 'success' > result.txt && git add result.txt && git commit -m 'harness commit'"),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    fake_notifier = FakeDiscordNotifier()
    service = HarnessExecutionService(issues=issues, discord_notifier=fake_notifier)
    service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    # Should have at least the "started" call (and also "completed" since this run succeeds)
    started_calls = [c for c in fake_notifier.calls if "Run Started" in str(c.get("title", ""))]
    assert len(started_calls) >= 1, f"Expected a 'Run Started' call, got: {fake_notifier.calls}"

    started = started_calls[0]
    assert started["title"] == "Run Started"
    assert "#8" in started["description"]
    assert "Execute agent harness" in started["description"]
    assert "demo" in started.get("description", "")
    assert "run-123" in started.get("description", "")
    # Greenish-blue color
    assert started["color"] == 0x1ABC9C

    # Verify "Run Completed" was also sent (the harness creates a commit so it succeeds)
    completed_calls = [c for c in fake_notifier.calls if "Run Completed" in str(c.get("title", ""))]
    assert len(completed_calls) >= 1, f"Expected a 'Run Completed' call, got: {fake_notifier.calls}"

    completed = completed_calls[0]
    assert completed["title"] == "Run Completed"
    assert "#8" in completed["description"]
    assert "demo" in completed.get("description", "")
    assert "run-123" in completed.get("description", "")
    # Green color
    assert completed["color"] == 0x57F287


def test_execution_env_context_delivery(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_test_git_repo(tmp_path)
    issues = get_mock_issues()

    # The harness will write the env vars to a file, add it, and commit it
    harnesses = {
        "local-agent": HarnessConfig(
            name="local-agent",
            command="bash",
            args_template=(
                "-c",
                "echo $BERSAMA_ISSUE_NUMBER:$BERSAMA_PARENT_PRD_NUMBER:$BERSAMA_PRD_BRANCH:$BERSAMA_IMPLEMENTATION_BRANCH > env.txt && git add env.txt && git commit -m 'env check'",
            ),
        )
    }
    repos = {
        "demo": RepoConfig(
            name="demo",
            repo_path=repo_path,
            main_branch="main",
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness="local-agent",
        )
    }
    config = AppConfig(repos=repos, harnesses=harnesses)

    service = HarnessExecutionService(issues=issues)
    result = service.execute_run(
        repo_name="demo",
        issue_number=8,
        config=config,
    )

    assert result.status == "succeeded"

    env_file = worktree_path / "env.txt"
    assert env_file.exists()
    assert env_file.read_text().strip() == "8:1:prd/1-parent-prd:impl/1/8-child-impl"
