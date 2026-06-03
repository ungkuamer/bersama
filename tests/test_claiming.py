import subprocess

from rangkai.claiming import (
    ClaimWorkspaceGateway,
    ImplementationClaimService,
    build_implementation_branch_name,
    upsert_claim_metadata,
)
from rangkai.github_issues import GitHubIssueRecord


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues: dict[int, GitHubIssueRecord] = {issue.number: issue for issue in issues}
        self.viewed_numbers: list[int] = []
        self.updated_bodies: list[tuple[int, str]] = []
        self.added_labels: list[tuple[int, tuple[str, ...]]] = []
        self.removed_labels: list[tuple[int, tuple[str, ...]]] = []
        self.added_comments: list[tuple[int, str]] = []
        self._post_update_hook: "callable | None" = None

    def set_post_update_hook(self, hook: "callable") -> None:
        self._post_update_hook = hook

    def view_issue(self, number: int) -> GitHubIssueRecord:
        self.viewed_numbers.append(number)
        return self.issues[number]

    def update_body(self, number: int, body: str) -> None:
        self.updated_bodies.append((number, body))
        # Reflect the update in the stored record so re-reads see the change.
        current = self.issues[number]
        self.issues[number] = GitHubIssueRecord(
            number=current.number,
            title=current.title,
            body=body,
            labels=current.labels,
            state=current.state,
        )
        if self._post_update_hook:
            self._post_update_hook(number, body)

    def add_labels(self, number: int, *labels: str) -> None:
        self.added_labels.append((number, labels))
        current = self.issues[number]
        self.issues[number] = GitHubIssueRecord(
            number=current.number,
            title=current.title,
            body=current.body,
            labels=tuple(sorted(set(current.labels + labels))),
            state=current.state,
        )

    def remove_labels(self, number: int, *labels: str) -> None:
        self.removed_labels.append((number, labels))
        current = self.issues[number]
        self.issues[number] = GitHubIssueRecord(
            number=current.number,
            title=current.title,
            body=current.body,
            labels=tuple(sorted(set(current.labels) - set(labels))),
            state=current.state,
        )

    def add_comment(self, number: int, body: str) -> None:
        self.added_comments.append((number, body))


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
    assert issue_gateway.added_labels == [(7, ("claimed",))]
    # First update: provisional claim with Claim Status setting up.
    # Second update: promoted to Active Claim.
    assert issue_gateway.updated_bodies == [
        (
            7,
            "## Parent PRD\n#5\n\n## What to Build\nClaim the issue.\n\n## Acceptance Criteria\n- [ ] It works.\n\n## Blocked By\nNone\n\n## Orchestration\n- Agent Run: run-123\n- Claimed At: 2026-05-29T09:30:00Z\n- Claim Status: setting up\n- Implementation Branch: impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
        ),
        (
            7,
            "## Parent PRD\n#5\n\n## What to Build\nClaim the issue.\n\n## Acceptance Criteria\n- [ ] It works.\n\n## Blocked By\nNone\n\n## Orchestration\n- Agent Run: run-123\n- Claimed At: 2026-05-29T09:30:00Z\n- Claim Status: active\n- Implementation Branch: impl/5/7-claim-implementation-issues-and-create-isolated-worktrees",
        ),
    ]
    # The issue was re-read after the provisional write (viewed twice total: initial + re-read).
    assert issue_gateway.viewed_numbers == [7, 5, 7]
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
    # The provisional body was written before the setup attempt.
    # After failure, a second body update records the Failed Claim Setup.
    assert len(issue_gateway.updated_bodies) == 2
    assert "Claim Status: setting up" in issue_gateway.updated_bodies[0][1]
    assert "Claim Status: failed claim" in issue_gateway.updated_bodies[1][1]
    # The issue was re-read after the provisional write.
    assert issue_gateway.viewed_numbers == [7, 5, 7]
    # A diagnostic comment was posted with Failed Claim Setup language.
    assert len(issue_gateway.added_comments) == 1
    assert "Failed Claim Setup" in issue_gateway.added_comments[0][1]


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


def test_claim_issue_detects_ownership_mismatch_on_re_read() -> None:
    """After writing provisional metadata, re-read must confirm ownership.

    If a competing Agent Run overwrites the provisional claim before the
    re-read, the losing Agent Run must stop without creating branch or
    worktree state.
    """
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
    # Simulate a competing Agent Run that overwrites the provisional metadata
    # immediately after the first write.
    def inject_competing_claim(issue_number: int, body: str) -> None:
        from rangkai.claiming import upsert_claim_metadata

        competing_body = upsert_claim_metadata(
            body,
            agent_run_id="run-competing",
            claimed_at="2026-05-29T09:31:00Z",
            implementation_branch="impl/5/7-competing-claim",
            claim_status="setting up",
        )
        issue_gateway.issues[issue_number] = GitHubIssueRecord(
            number=issue_number,
            title=issue_gateway.issues[issue_number].title,
            body=competing_body,
            labels=issue_gateway.issues[issue_number].labels,
            state=issue_gateway.issues[issue_number].state,
        )

    issue_gateway.set_post_update_hook(inject_competing_claim)

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
    assert "Ownership mismatch" in result.failure_message
    # The provisional write happened.
    assert len(issue_gateway.updated_bodies) == 2
    assert "Claim Status: setting up" in issue_gateway.updated_bodies[0][1]
    assert "Claim Status: failed claim" in issue_gateway.updated_bodies[1][1]
    assert issue_gateway.added_labels == [(7, ("needs-triage",))]
    assert len(issue_gateway.added_comments) == 1
    assert "Failed Claim Setup" in issue_gateway.added_comments[0][1]
    # No branch or worktree commands were issued (after hook, re-read fails).
    git_command_args = " ".join(" ".join(cmd) for cmd, _ in git_runner.commands)
    assert "branch" not in git_command_args
    assert "worktree" not in git_command_args


def test_claim_issue_marks_needs_triage_when_branch_setup_fails() -> None:
    """Branch setup failure records Failed Claim Setup diagnostics."""
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
            "fetch",
            "origin",
            "prd/5-prepare-prd",
        ),
        "branch setup failed",
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
    assert result.failure_message == "branch setup failed"
    assert issue_gateway.added_labels == [(7, ("needs-triage",))]
    # The provisional body was written before the setup attempt.
    # After failure, a second body update records the Failed Claim Setup.
    assert len(issue_gateway.updated_bodies) == 2
    assert "Claim Status: setting up" in issue_gateway.updated_bodies[0][1]
    assert "Claim Status: failed claim" in issue_gateway.updated_bodies[1][1]
    # The issue was re-read after the provisional write.
    assert issue_gateway.viewed_numbers == [7, 5, 7]
    # A diagnostic comment was posted.
    assert len(issue_gateway.added_comments) == 1
    assert "Failed Claim Setup" in issue_gateway.added_comments[0][1]


def test_claim_issue_stops_when_provisional_lifecycle_mutation_fails() -> None:
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

    original_update_body = issue_gateway.update_body

    def fail_first_update(number: int, body: str) -> None:
        if "Claim Status: setting up" in body:
            raise RuntimeError("Mutation outcome is ambiguous: body update did not confirm whether the change applied.")
        original_update_body(number, body)

    issue_gateway.update_body = fail_first_update
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

    assert result.succeeded is False
    assert "Mutation outcome is ambiguous" in result.failure_message
    assert issue_gateway.added_labels == [(7, ("needs-triage",))]
    assert len(issue_gateway.added_comments) == 1
    assert "Failed Claim Setup" in issue_gateway.added_comments[0][1]
    assert "Lifecycle Mutation failed before repository setup" in issue_gateway.added_comments[0][1]
    assert len(issue_gateway.updated_bodies) == 1
    assert "Claim Status: failed claim" in issue_gateway.updated_bodies[0][1]
    assert git_runner.commands == []


def test_competing_claims_only_one_reaches_active_claim() -> None:
    """When two Agent Runs attempt to claim the same issue, only one succeeds.

    The second attempt must fail because the first already wrote claim
    metadata, even if it has not yet been promoted to Active Claim.
    """
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
    service_a = ImplementationClaimService(
        issues=issue_gateway,
        workspace=workspace,
        now_provider=lambda: "2026-05-29T09:30:00Z",
    )
    service_b = ImplementationClaimService(
        issues=issue_gateway,
        workspace=workspace,
        now_provider=lambda: "2026-05-29T09:30:01Z",
    )

    # First claim succeeds.
    result_a = service_a.claim_issue(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=7,
        agent_run_id="run-A",
    )
    assert result_a.succeeded is True

    # Second claim fails because the issue already has claim metadata.
    result_b = service_b.claim_issue(
        repo_path="/repos/demo",
        worktree_root="/worktrees/demo",
        issue_number=7,
        agent_run_id="run-B",
    )
    assert result_b.succeeded is False
    assert "not ready for agent claim" in result_b.failure_message
