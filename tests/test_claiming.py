import subprocess

from bersama.claiming import (
    ClaimWorkspaceGateway,
    ImplementationClaimService,
    build_implementation_branch_name,
    upsert_claim_metadata,
)
from bersama.github_issues import GitHubIssueRecord


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}
        self.viewed_numbers: list[int] = []
        self.updated_bodies: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, tuple[str, ...]]] = []
        self.removed_labels: list[tuple[int, tuple[str, ...]]] = []

    def view_issue(self, number: int) -> GitHubIssueRecord:
        self.viewed_numbers.append(number)
        return self.issues[number]

    def update_body(self, number: int, body: str) -> None:
        self.updated_bodies.append((number, body))

    def add_labels(self, number: int, *labels: str) -> None:
        self.added_labels.append((number, labels))

    def remove_labels(self, number: int, *labels: str) -> None:
        self.removed_labels.append((number, labels))

    def add_comment(self, number: int, body: str) -> None:
        pass


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


def test_build_implementation_branch_name_uses_canonical_format() -> None:
    assert (
        build_implementation_branch_name(
            5,
            7,
            "Claim Implementation Issues and create isolated worktrees!",
        )
        == "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees"
    )


def test_upsert_claim_metadata_adds_orchestration_section() -> None:
    body = "## What to Build\n\nShip the feature."

    updated = upsert_claim_metadata(
        body,
        agent_run_id="run-123",
        claimed_at="2026-05-29T09:30:00Z",
        implementation_branch="impl/1/7-ship-the-feature",
    )

    assert updated.endswith(
        "## Orchestration\n"
        "- Agent Run: run-123\n"
        "- Claimed At: 2026-05-29T09:30:00Z\n"
        "- Implementation Branch: impl/1/7-ship-the-feature"
    )


def test_claim_issue_updates_metadata_flips_ready_label_and_creates_worktree() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=7,
            title="Claim Implementation Issues and create isolated worktrees",
            body="""
## Parent PRD
#5

## What to Build
Claim the issue.

## Acceptance Criteria
- [ ] It works.

## Blocked By
None
""".strip(),
            labels=("implementation", "ready-for-agent"),
            state="open",
        ),
        GitHubIssueRecord(
            number=5,
            title="Prepare PRD",
            body="""
## Orchestration
- PRD Branch: prd/5-prepare-prd
""".strip(),
            labels=("prd",),
            state="open",
        ),
    )
    git_runner = FakeGitRunner()
    workspace = ClaimWorkspaceGateway(runner=git_runner)
    service = ImplementationClaimService(
        issues=issue_gateway,
        workspace=workspace,
        now_provider=lambda: "2026-05-29T09:30:00Z",
    )

    result = service.claim_issue(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=7,
        agent_run_id="run-123",
    )

    assert result.succeeded is True
    assert (
        result.implementation_branch
        == "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees"
    )
    assert result.worktree_path == "/worktrees/demo/issue-7"
    assert issue_gateway.removed_labels == [(7, ("ready-for-agent",))]
    assert issue_gateway.updated_bodies == [
        (
            7,
            "## Parent PRD\n#5\n\n## What to Build\nClaim the issue.\n\n## Acceptance Criteria\n- [ ] It works.\n\n## Blocked By\nNone\n\n## Orchestration\n- Agent Run: run-123\n- Claimed At: 2026-05-29T09:30:00Z\n- Implementation Branch: impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
        )
    ]
    assert git_runner.commands == [
        (
            (
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
            ),
            "/repos/demo",
        ),
        (("git", "fetch", "origin", "prd/5-prepare-prd"), "/repos/demo"),
        (
            (
                "git",
                "branch",
                "--create-reflog",
                "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
                "origin/prd/5-prepare-prd",
            ),
            "/repos/demo",
        ),
        (
            (
                "git",
                "push",
                "origin",
                "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees:impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
            ),
            "/repos/demo",
        ),
        (
            (
                "mkdir",
                "-p",
                "/worktrees/demo",
            ),
            "/repos/demo",
        ),
        (
            (
                "git",
                "fetch",
                "origin",
                "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
            ),
            "/repos/demo",
        ),
        (
            (
                "git",
                "worktree",
                "add",
                "/worktrees/demo/issue-7",
                "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
            ),
            "/repos/demo",
        ),
    ]


def test_claim_issue_marks_needs_triage_when_worktree_setup_fails() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=7,
            title="Claim Implementation Issues and create isolated worktrees",
            body="""
## Parent PRD
#5

## What to Build
Claim the issue.

## Acceptance Criteria
- [ ] It works.

## Blocked By
None
""".strip(),
            labels=("implementation", "ready-for-agent"),
            state="open",
        ),
        GitHubIssueRecord(
            number=5,
            title="Prepare PRD",
            body="""
## Orchestration
- PRD Branch: prd/5-prepare-prd
""".strip(),
            labels=("prd",),
            state="open",
        ),
    )
    git_runner = FakeGitRunner()
    git_runner.fail(
        (
            "git",
            "worktree",
            "add",
            "/worktrees/demo/issue-7",
            "impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
        ),
        "worktree setup failed",
    )
    workspace = ClaimWorkspaceGateway(runner=git_runner)
    service = ImplementationClaimService(
        issues=issue_gateway,
        workspace=workspace,
        now_provider=lambda: "2026-05-29T09:30:00Z",
    )

    result = service.claim_issue(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=7,
        agent_run_id="run-123",
    )

    assert result.succeeded is False
    assert result.failure_message == "worktree setup failed"
    assert issue_gateway.added_labels == [(7, ("needs-triage",))]


def test_claim_issue_requires_prepared_parent_prd() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=7,
            title="Claim Implementation Issues and create isolated worktrees",
            body="""
## Parent PRD
#5

## What to Build
Claim the issue.

## Acceptance Criteria
- [ ] It works.

## Blocked By
None
""".strip(),
            labels=("implementation", "ready-for-agent"),
            state="open",
        ),
        GitHubIssueRecord(
            number=5,
            title="Prepare PRD",
            body="## Problem Statement\n\nNo orchestration yet.",
            labels=("prd",),
            state="open",
        ),
    )
    workspace = ClaimWorkspaceGateway(runner=FakeGitRunner())
    service = ImplementationClaimService(
        issues=issue_gateway,
        workspace=workspace,
        now_provider=lambda: "2026-05-29T09:30:00Z",
    )

    result = service.claim_issue(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=7,
        agent_run_id="run-123",
    )

    assert result.succeeded is False
    assert result.failure_message == "Parent PRD issue is not prepared."
