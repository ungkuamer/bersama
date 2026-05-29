from __future__ import annotations

import json
from pathlib import Path
import subprocess

from bersama.github_issues import GitHubIssueRecord
from bersama.integration import (
    IntegrationService,
    IntegrationWorkspaceGateway,
    MergeConflictError,
    PushError,
    UpdateError,
)


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}
        self.comments: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, tuple[str, ...]]] = []
        self.removed_labels: list[tuple[int, tuple[str, ...]]] = []
        self.closed_issues: list[int] = []

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self.issues[number]

    def add_comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def add_labels(self, number: int, *labels: str) -> None:
        self.added_labels.append((number, labels))

    def remove_labels(self, number: int, *labels: str) -> None:
        self.removed_labels.append((number, labels))

    def close_issue(self, number: int) -> None:
        self.closed_issues.append(number)


class FakeGitRunner:
    def __init__(self, outputs: dict[tuple[str, ...], str] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[tuple[tuple[str, ...], str]] = []
        self.failures: dict[tuple[str, ...], subprocess.CalledProcessError] = {}

    def fail(self, command: tuple[str, ...], stderr: str) -> None:
        self.failures[command] = subprocess.CalledProcessError(
            1, command, stderr=stderr
        )

    def __call__(self, command: tuple[str, ...], *, cwd: str) -> str:
        self.commands.append((command, cwd))
        if command in self.failures:
            raise self.failures[command]
        return self.outputs.get(command, "")


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


def test_integrate_issue_success_flow(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()
    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is True
    assert result.status == "succeeded"
    assert result.implementation_branch == "impl/1/8-child-impl"
    assert result.prd_branch == "prd/1-parent-prd"
    assert len(issues.comments) == 0
    assert issues.closed_issues == [8]
    assert len(issues.added_labels) == 0

    assert runner.commands == [
        (("git", "fetch", "origin"), str(worktree_path)),
        (
            (
                "git",
                "merge",
                "origin/prd/1-parent-prd",
                "-m",
                "Update implementation branch against latest prd/1-parent-prd",
            ),
            str(worktree_path),
        ),
        (("git", "push", "origin", "impl/1/8-child-impl"), str(worktree_path)),
        (
            (
                "git",
                "push",
                "origin",
                "impl/1/8-child-impl:prd/1-parent-prd",
            ),
            str(worktree_path),
        ),
    ]


def test_integrate_issue_merge_conflict(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()
    merge_cmd = (
        "git",
        "merge",
        "origin/prd/1-parent-prd",
        "-m",
        "Update implementation branch against latest prd/1-parent-prd",
    )
    runner.fail(
        merge_cmd,
        "CONFLICT (content): Merge conflict in dummy.txt. Automatic merge failed; fix conflicts and then commit the result.",
    )

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.failure_type == "merge_conflict"
    assert "Merge conflict" in result.failure_message
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1
    assert (
        "Integration failed for implementation branch `impl/1/8-child-impl`"
        in issues.comments[0][1]
    )
    assert "**Diagnostics:**" in issues.comments[0][1]

    # Verify git merge --abort was called
    assert (("git", "merge", "--abort"), str(worktree_path)) in runner.commands


def test_integrate_issue_update_failure(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()
    merge_cmd = (
        "git",
        "merge",
        "origin/prd/1-parent-prd",
        "-m",
        "Update implementation branch against latest prd/1-parent-prd",
    )
    runner.fail(merge_cmd, "fatal: some general git error")

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.failure_type == "update_failure"
    assert "Failed to update" in result.failure_message
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1


def test_integrate_issue_push_failure(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()
    push_cmd = ("git", "push", "origin", "impl/1/8-child-impl")
    runner.fail(push_cmd, "fatal: remote hung up unexpectedly")

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.failure_type == "push_failure"
    assert "Push/Merge failure" in result.failure_message
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1


def setup_real_test_git_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    # 1. Initialize main remote repo
    remote_path = tmp_path / "remote"
    remote_path.mkdir()
    subprocess.run(
        ["git", "init", "--bare"], cwd=remote_path, check=True, capture_output=True
    )

    # 2. Clone to local repo
    repo_path = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", str(remote_path), str(repo_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Make initial commit on main
    dummy = repo_path / "dummy.txt"
    dummy.write_text("initial")
    subprocess.run(
        ["git", "add", "dummy.txt"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create parent PRD branch and push
    prd_branch = "prd/1-parent-prd"
    subprocess.run(
        ["git", "checkout", "-b", prd_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    dummy.write_text("prd change")
    subprocess.run(
        ["git", "add", "dummy.txt"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "prd commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", prd_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create implementation branch and push
    impl_branch = "impl/1/8-child-impl"
    subprocess.run(
        ["git", "checkout", "-b", impl_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    dummy2 = repo_path / "dummy2.txt"
    dummy2.write_text("harness work")
    subprocess.run(
        ["git", "add", "dummy2.txt"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "harness commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", impl_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Checkout main so we can create worktree
    subprocess.run(
        ["git", "checkout", "main"], cwd=repo_path, check=True, capture_output=True
    )

    # Setup worktree root and add worktree for implementation branch
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), impl_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Configure user on worktree
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
    )

    return repo_path, worktree_root, worktree_path


def test_real_git_integration_success(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_real_test_git_repo(tmp_path)
    issues = get_mock_issues()

    workspace = IntegrationWorkspaceGateway()
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path=str(repo_path),
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is True
    assert result.status == "succeeded"
    assert issues.closed_issues == [8]

    # Verify that the implementation branch was pushed to remote and integrated into remote prd branch!
    # Let's run git log origin/prd/1-parent-prd to make sure it includes the harness commit "harness commit"
    log_res = subprocess.run(
        ["git", "log", "origin/prd/1-parent-prd", "--oneline"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "harness commit" in log_res.stdout
