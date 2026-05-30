from __future__ import annotations

import json
from pathlib import Path
import subprocess

from bersama.github_issues import GitHubIssueRecord
from bersama.integration import (
    IntegrationService,
    IntegrationWorkspaceGateway,
    MergeConflictError,
    PrCreationError,
    PrMergeError,
    PushError,
    UpdateError,
)
from bersama.command_executor import CommandPhase, CommandResult


class RecordingCommandExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], CommandPhase, str]] = []
        self.results: dict[tuple[str, ...], CommandResult] = {}

    def execute(self, command: tuple[str, ...], phase: CommandPhase, *, cwd: str) -> CommandResult:
        self.calls.append((command, phase, cwd))
        return self.results.get(
            command,
            CommandResult(
                command=command,
                phase=phase,
                stdout="",
                stderr="",
                exit_code=0,
                timed_out=False,
                retries_attempted=0,
                cwd=cwd,
                diagnostics=None,
            ),
        )


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}
        self.comments: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, tuple[str, ...]]] = []
        self.removed_labels: list[tuple[int, tuple[str, ...]]] = []
        self.closed_issues: list[int] = []
        self.updated_bodies: list[tuple[int, str]] = []

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

    def update_body(self, number: int, body: str) -> None:
        self.updated_bodies.append((number, body))
        # Also update the in-memory record so subsequent view_issue returns updated body
        if number in self.issues:
            old = self.issues[number]
            self.issues[number] = GitHubIssueRecord(
                number=old.number,
                title=old.title,
                body=body,
                labels=old.labels,
                state=old.state,
            )


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

    # Pre-configure the gh pr create output so it returns a PR number
    expected_pr_create_cmd = (
        "gh",
        "pr",
        "create",
        "--head",
        "impl/1/8-child-impl",
        "--base",
        "prd/1-parent-prd",
        "--title",
        "Integration: #8 into prd/1-parent-prd",
        "--body",
        "Automated integration of implementation branch `impl/1/8-child-impl` into PRD branch `prd/1-parent-prd`.",
    )
    expected_pr_merge_cmd = (
        "gh",
        "pr",
        "merge",
        "42",
        "--squash",
    )
    runner.outputs[expected_pr_create_cmd] = "https://github.com/owner/repo/pull/42\n"

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
        (expected_pr_create_cmd, str(worktree_path)),
        (expected_pr_merge_cmd, str(worktree_path)),
    ]


def test_integration_workspace_gateway_routes_commands_through_bounded_executor_with_expected_phases() -> None:
    executor = RecordingCommandExecutor()
    pr_create_cmd = (
        "gh",
        "pr",
        "create",
        "--head",
        "impl/1/8-child-impl",
        "--base",
        "prd/1-parent-prd",
        "--title",
        "Integration: #8 into prd/1-parent-prd",
        "--body",
        "Automated integration.",
    )
    pr_view_cmd = (
        "gh",
        "pr",
        "view",
        "42",
        "--json",
        "state,mergeable,closed,statusCheckRollup",
    )
    executor.results[pr_create_cmd] = CommandResult(
        command=pr_create_cmd,
        phase=CommandPhase.LIFECYCLE_MUTATION,
        stdout="https://github.com/owner/repo/pull/42\n",
        stderr="",
        exit_code=0,
        timed_out=False,
        retries_attempted=0,
        cwd="/worktrees/demo/issue-8",
        diagnostics=None,
    )
    executor.results[pr_view_cmd] = CommandResult(
        command=pr_view_cmd,
        phase=CommandPhase.DISCOVERY,
        stdout='{"state":"OPEN","mergeable":"MERGEABLE","closed":false,"statusCheckRollup":[]}',
        stderr="",
        exit_code=0,
        timed_out=False,
        retries_attempted=0,
        cwd="/worktrees/demo/issue-8",
        diagnostics=None,
    )

    workspace = IntegrationWorkspaceGateway(command_executor=executor)

    workspace.update_branch(
        worktree_path="/worktrees/demo/issue-8",
        implementation_branch="impl/1/8-child-impl",
        prd_branch="prd/1-parent-prd",
    )
    workspace.push_branch(
        worktree_path="/worktrees/demo/issue-8",
        branch_name="impl/1/8-child-impl",
    )
    assert (
        workspace.create_pr(
            worktree_path="/worktrees/demo/issue-8",
            implementation_branch="impl/1/8-child-impl",
            prd_branch="prd/1-parent-prd",
            title="Integration: #8 into prd/1-parent-prd",
            body="Automated integration.",
        )
        == "42"
    )
    assert (
        workspace.check_pr(
            worktree_path="/worktrees/demo/issue-8",
            pr_number="42",
        )["mergeable"]
        == "MERGEABLE"
    )
    workspace.merge_pr(
        worktree_path="/worktrees/demo/issue-8",
        pr_number="42",
    )

    assert executor.calls == [
        (("git", "fetch", "origin"), CommandPhase.DISCOVERY, "/worktrees/demo/issue-8"),
        (
            (
                "git",
                "merge",
                "origin/prd/1-parent-prd",
                "-m",
                "Update implementation branch against latest prd/1-parent-prd",
            ),
            CommandPhase.LIFECYCLE_MUTATION,
            "/worktrees/demo/issue-8",
        ),
        (("git", "push", "origin", "impl/1/8-child-impl"), CommandPhase.LIFECYCLE_MUTATION, "/worktrees/demo/issue-8"),
        (pr_create_cmd, CommandPhase.LIFECYCLE_MUTATION, "/worktrees/demo/issue-8"),
        (pr_view_cmd, CommandPhase.DISCOVERY, "/worktrees/demo/issue-8"),
        (("gh", "pr", "merge", "42", "--squash"), CommandPhase.LIFECYCLE_MUTATION, "/worktrees/demo/issue-8"),
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


def test_integrate_issue_pr_creation_failure(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()
    pr_create_cmd = (
        "gh", "pr", "create",
        "--head", "impl/1/8-child-impl",
        "--base", "prd/1-parent-prd",
        "--title", "Integration: #8 into prd/1-parent-prd",
        "--body", "Automated integration of implementation branch `impl/1/8-child-impl` into PRD branch `prd/1-parent-prd`.",
    )
    runner.fail(pr_create_cmd, "gh: pull request create failed")

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
    assert "PR creation failure" in result.failure_message
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1


def test_integrate_issue_pr_merge_failure(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues()
    runner = FakeGitRunner()

    pr_create_cmd = (
        "gh", "pr", "create",
        "--head", "impl/1/8-child-impl",
        "--base", "prd/1-parent-prd",
        "--title", "Integration: #8 into prd/1-parent-prd",
        "--body", "Automated integration of implementation branch `impl/1/8-child-impl` into PRD branch `prd/1-parent-prd`.",
    )
    runner.outputs[pr_create_cmd] = "https://github.com/owner/repo/pull/42\n"

    # gh pr merge fails
    pr_merge_cmd = ("gh", "pr", "merge", "42", "--squash")
    runner.fail(pr_merge_cmd, "gh: pull request merge failed")

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
    assert "PR merge failure" in result.failure_message
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


class HybridGitRunner:
    """A GitRunner that delegates real git commands to subprocess but fakes
    gh commands for testing PR workflows against a local bare repo.

    On gh pr create: returns a fake PR number and pushes the implementation
    branch as the PRD branch (simulating what a real PR merge would do).
    On gh pr merge: does nothing (the merge was effectively done at create time
    for test purposes).
    """

    def __init__(self, repo_path: str) -> None:
        self._repo_path = repo_path
        self.commands: list[tuple[tuple[str, ...], str]] = []

    def __call__(self, command: tuple[str, ...], *, cwd: str) -> str:
        self.commands.append((command, cwd))
        if command[0] == "gh":
            return self._handle_gh(command, cwd=cwd)
        # Real git commands
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return completed.stdout

    def _handle_gh(self, command: tuple[str, ...], *, cwd: str) -> str:
        if command[:3] == ("gh", "pr", "create"):
            # Parse --head and --base
            head_idx = command.index("--head") + 1
            base_idx = command.index("--base") + 1
            head_branch = command[head_idx]
            base_branch = command[base_idx]
            # Simulate the PR merge by pushing head to base
            subprocess.run(
                ("git", "push", "origin", f"{head_branch}:{base_branch}"),
                check=True,
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            return "42\n"  # Fake PR number
        elif command[:3] == ("gh", "pr", "merge"):
            # Already merged at create time in our simulation
            return "Pull request #42 merged\n"
        raise RuntimeError(f"Unexpected gh command: {command}")


def test_real_git_integration_success(tmp_path: Path) -> None:
    repo_path, worktree_root, worktree_path = setup_real_test_git_repo(tmp_path)
    issues = get_mock_issues()

    runner = HybridGitRunner(repo_path=str(repo_path))
    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.integrate_issue(
        repo_path=str(repo_path),
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.succeeded is True
    assert result.status == "succeeded"
    assert issues.closed_issues == [8]

    # Verify that the implementation branch was integrated into remote PRD branch
    log_res = subprocess.run(
        ["git", "log", "origin/prd/1-parent-prd", "--oneline"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "harness commit" in log_res.stdout

    # Verify the gh commands were called
    assert any(
        cmd[:2] == ("gh", "pr") for cmd, _ in runner.commands
    ), "Expected gh pr commands to be invoked"


# ── Async Integration Tests (create_integration_pr + poll_integration_pr) ──

def get_mock_issues_for_async() -> FakeIssueGateway:
    """Mock issues where #8 is ready for async integration (has claim metadata)."""
    impl_body = """
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
""".strip()

    impl_issue_record = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body,
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


def test_create_integration_pr_success(tmp_path: Path) -> None:
    """create_integration_pr updates branch, pushes, creates PR, writes orchestration."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues_for_async()
    runner = FakeGitRunner()

    pr_create_cmd = (
        "gh", "pr", "create",
        "--head", "impl/1/8-child-impl",
        "--base", "prd/1-parent-prd",
        "--title", "Integration: #8 into prd/1-parent-prd",
        "--body", "Automated integration of implementation branch `impl/1/8-child-impl` into PRD branch `prd/1-parent-prd`.",
    )
    runner.outputs[pr_create_cmd] = "https://github.com/owner/repo/pull/42\n"

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.create_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "pending_validation"
    assert result.pr_number == "42"
    assert result.implementation_branch == "impl/1/8-child-impl"
    assert result.prd_branch == "prd/1-parent-prd"

    # Orchestration should be written with PR number and pending_validation status
    assert len(issues.updated_bodies) == 1
    updated_num, updated_body = issues.updated_bodies[0]
    assert updated_num == 8
    assert "Integration PR: #42" in updated_body
    assert "Integration Status: pending_validation" in updated_body

    # No issue was closed yet (that happens in poll phase)
    assert issues.closed_issues == []
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0


def test_create_integration_pr_merge_conflict(tmp_path: Path) -> None:
    """create_integration_pr handles merge conflict by writing failed status."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    issues = get_mock_issues_for_async()
    runner = FakeGitRunner()
    merge_cmd = (
        "git", "merge",
        "origin/prd/1-parent-prd",
        "-m",
        "Update implementation branch against latest prd/1-parent-prd",
    )
    runner.fail(merge_cmd, "CONFLICT (content): Merge conflict in dummy.txt")

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.create_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "failed"
    assert result.failure_type == "merge_conflict"
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1


def test_poll_integration_pr_checks_pass_and_merge(tmp_path: Path) -> None:
    """poll_integration_pr merges and closes when all PR status checks pass."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_with_pr = """
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
- Integration PR: #42
- Integration Status: pending_validation
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_with_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    # gh pr view returns all checks green
    pr_view_cmd = (
        "gh", "pr", "view", "42",
        "--json", "state,mergeable,closed,statusCheckRollup",
    )
    runner.outputs[pr_view_cmd] = '{"state":"OPEN","mergeable":"MERGEABLE","closed":false,"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"}]}'

    # gh pr merge succeeds
    pr_merge_cmd = ("gh", "pr", "merge", "42", "--squash")
    runner.outputs[pr_merge_cmd] = "Pull request #42 merged\n"

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "succeeded"
    assert result.pr_number == "42"
    assert issues.closed_issues == [8]
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0


def test_poll_integration_pr_checks_failed(tmp_path: Path) -> None:
    """poll_integration_pr marks needs-triage when PR status checks fail."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_with_pr = """
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
- Integration PR: #42
- Integration Status: pending_validation
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_with_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    # gh pr view returns failed checks
    pr_view_cmd = (
        "gh", "pr", "view", "42",
        "--json", "state,mergeable,closed,statusCheckRollup",
    )
    runner.outputs[pr_view_cmd] = '{"state":"OPEN","mergeable":"MERGEABLE","closed":false,"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"FAILURE"}]}'

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "failed"
    assert result.failure_type == "checks_failed"
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1
    assert "CI/CD checks failed" in issues.comments[0][1]

    # Orchestration status updated to failed
    assert len(issues.updated_bodies) == 1
    _, updated_body = issues.updated_bodies[0]
    assert "Integration Status: failed" in updated_body


def test_poll_integration_pr_skips_when_not_pending_validation(tmp_path: Path) -> None:
    """poll_integration_pr skips issues whose status is not pending_validation."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_merged = """
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
- Integration PR: #42
- Integration Status: merged
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_merged,
        labels=("implementation",),
        state="closed",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "skipped"
    # No side effects
    assert issues.closed_issues == []
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0
    assert len(runner.commands) == 0


def test_poll_integration_pr_skips_when_no_integration_pr(tmp_path: Path) -> None:
    """poll_integration_pr skips issues without an integration PR."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    # No integration fields at all
    impl_body_no_pr = """
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
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_no_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "skipped"
    assert issues.closed_issues == []
    assert len(runner.commands) == 0


def test_poll_integration_pr_merge_conflict_detected(tmp_path: Path) -> None:
    """poll_integration_pr detects PR conflicts and marks needs-triage."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_with_pr = """
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
- Integration PR: #42
- Integration Status: pending_validation
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_with_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    # PR is conflicting
    pr_view_cmd = (
        "gh", "pr", "view", "42",
        "--json", "state,mergeable,closed,statusCheckRollup",
    )
    runner.outputs[pr_view_cmd] = '{"state":"OPEN","mergeable":"CONFLICTING","closed":false,"statusCheckRollup":[]}'

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "failed"
    assert result.failure_type == "merge_conflict"
    assert issues.closed_issues == []
    assert issues.added_labels == [(8, ("needs-triage",))]
    assert len(issues.comments) == 1
    assert "merge conflict" in issues.comments[0][1].lower()


def test_poll_integration_pr_checks_in_progress_skips(tmp_path: Path) -> None:
    """poll_integration_pr skips when checks are still in progress (not yet completed)."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_with_pr = """
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
- Integration PR: #42
- Integration Status: pending_validation
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_with_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    # Checks are in progress (QUEUED, not COMPLETED)
    pr_view_cmd = (
        "gh", "pr", "view", "42",
        "--json", "state,mergeable,closed,statusCheckRollup",
    )
    runner.outputs[pr_view_cmd] = '{"state":"OPEN","mergeable":"MERGEABLE","closed":false,"statusCheckRollup":[{"name":"build","status":"IN_PROGRESS","conclusion":""}]}'

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "skipped"
    # No side effects — checks still running, don't merge or fail
    assert issues.closed_issues == []
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0


def test_poll_integration_pr_already_merged_externally(tmp_path: Path) -> None:
    """poll_integration_pr closes issue when PR was already merged externally."""
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree_path = worktree_root / "issue-8"
    worktree_path.mkdir()

    impl_body_with_pr = """
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
- Integration PR: #42
- Integration Status: pending_validation
""".strip()

    impl_issue = GitHubIssueRecord(
        number=8,
        title="Execute agent harness",
        body=impl_body_with_pr,
        labels=("implementation",),
        state="open",
    )
    parent_prd = GitHubIssueRecord(
        number=1,
        title="Parent PRD Title",
        body="## Problem Statement\nParent PRD.\n\n## Orchestration\n- PRD Branch: prd/1-parent-prd",
        labels=("prd",),
        state="open",
    )
    issues = FakeIssueGateway(impl_issue, parent_prd)
    runner = FakeGitRunner()

    # PR was merged (closed + merged)
    pr_view_cmd = (
        "gh", "pr", "view", "42",
        "--json", "state,mergeable,closed,statusCheckRollup",
    )
    runner.outputs[pr_view_cmd] = '{"state":"MERGED","mergeable":"UNKNOWN","closed":true,"statusCheckRollup":[]}'

    workspace = IntegrationWorkspaceGateway(runner=runner)
    service = IntegrationService(issues=issues, workspace=workspace)

    result = service.poll_integration_pr(
        repo_path="/repos/demo",
        worktree_root=str(worktree_root),
        issue_number=8,
    )

    assert result.status == "succeeded"
    assert issues.closed_issues == [8]
    assert len(issues.added_labels) == 0
    assert len(issues.comments) == 0
