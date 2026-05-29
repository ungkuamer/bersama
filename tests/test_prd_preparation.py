import subprocess

from bersama.github_issues import GitHubIssueGateway, GitHubIssueRecord
from bersama.prd_preparation import (
    GitWorkspaceGateway,
    PrdPreparationService,
    build_prd_branch_name,
    upsert_prd_branch_metadata,
)


class FakeIssueGateway:
    def __init__(self, issue: GitHubIssueRecord) -> None:
        self.issue = issue
        self.viewed_numbers: list[int] = []
        self.updated_bodies: list[tuple[int, str]] = []

    def view_issue(self, number: int) -> GitHubIssueRecord:
        self.viewed_numbers.append(number)
        return self.issue

    def update_body(self, number: int, body: str) -> None:
        self.updated_bodies.append((number, body))


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


def test_build_prd_branch_name_slugifies_title() -> None:
    assert (
        build_prd_branch_name(5, "Prepare PRD Issues with PRD branches!")
        == "prd/5-prepare-prd-issues-with-prd-branches"
    )


def test_upsert_prd_branch_metadata_adds_orchestration_section() -> None:
    body = "## Problem Statement\n\nCoordinate agent work."

    updated = upsert_prd_branch_metadata(body, "prd/1-coordinate-agent-work")

    assert updated.endswith("## Orchestration\n- PRD Branch: prd/1-coordinate-agent-work")


def test_prepare_issue_reuses_existing_branch_metadata() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=1,
            title="Build LangGraph agent orchestration system",
            body="""
## Problem Statement

Coordinate agent work.

## Orchestration
- PRD Branch: prd/1-build-langgraph-agent-orchestration-system
""".strip(),
            labels=("prd",),
            state="open",
        )
    )
    workspace = GitWorkspaceGateway(runner=FakeGitRunner())
    service = PrdPreparationService(issues=issue_gateway, workspace=workspace)

    result = service.prepare_issue(
        repo_path="/repos/demo",
        main_branch="main",
        issue_number=1,
    )

    assert result.succeeded is True
    assert result.prd_branch == "prd/1-build-langgraph-agent-orchestration-system"
    assert result.reused_existing_branch is True
    assert result.updated_issue_body is False
    assert issue_gateway.updated_bodies == []


def test_prepare_issue_creates_branch_pushes_remote_and_updates_body() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=1,
            title="Build LangGraph agent orchestration system",
            body="## Problem Statement\n\nCoordinate agent work.",
            labels=("prd",),
            state="open",
        )
    )
    git_runner = FakeGitRunner()
    workspace = GitWorkspaceGateway(runner=git_runner)
    service = PrdPreparationService(issues=issue_gateway, workspace=workspace)

    result = service.prepare_issue(
        repo_path="/repos/demo",
        main_branch="main",
        issue_number=1,
    )

    assert result.succeeded is True
    assert result.prd_branch == "prd/1-build-langgraph-agent-orchestration-system"
    assert result.reused_existing_branch is False
    assert result.updated_issue_body is True
    assert git_runner.commands == [
        (("git", "ls-remote", "--heads", "origin", "prd/1-build-langgraph-agent-orchestration-system"), "/repos/demo"),
        (("git", "fetch", "origin", "main"), "/repos/demo"),
        (
            (
                "git",
                "branch",
                "--create-reflog",
                "prd/1-build-langgraph-agent-orchestration-system",
                "origin/main",
            ),
            "/repos/demo",
        ),
        (
            (
                "git",
                "push",
                "origin",
                "prd/1-build-langgraph-agent-orchestration-system:prd/1-build-langgraph-agent-orchestration-system",
            ),
            "/repos/demo",
        ),
    ]
    assert issue_gateway.updated_bodies == [
        (
            1,
            "## Problem Statement\n\nCoordinate agent work.\n\n## Orchestration\n- PRD Branch: prd/1-build-langgraph-agent-orchestration-system",
        )
    ]


def test_prepare_issue_reuses_existing_remote_branch_and_updates_body() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=1,
            title="Build LangGraph agent orchestration system",
            body="## Problem Statement\n\nCoordinate agent work.",
            labels=("prd",),
            state="open",
        )
    )
    git_runner = FakeGitRunner(
        outputs={
            (
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "prd/1-build-langgraph-agent-orchestration-system",
            ): "abc123\trefs/heads/prd/1-build-langgraph-agent-orchestration-system\n"
        }
    )
    workspace = GitWorkspaceGateway(runner=git_runner)
    service = PrdPreparationService(issues=issue_gateway, workspace=workspace)

    result = service.prepare_issue(
        repo_path="/repos/demo",
        main_branch="main",
        issue_number=1,
    )

    assert result.succeeded is True
    assert result.reused_existing_branch is True
    assert result.updated_issue_body is True
    assert git_runner.commands == [
        (("git", "ls-remote", "--heads", "origin", "prd/1-build-langgraph-agent-orchestration-system"), "/repos/demo")
    ]


def test_prepare_issue_returns_failure_when_branch_creation_fails() -> None:
    issue_gateway = FakeIssueGateway(
        GitHubIssueRecord(
            number=1,
            title="Build LangGraph agent orchestration system",
            body="## Problem Statement\n\nCoordinate agent work.",
            labels=("prd",),
            state="open",
        )
    )
    git_runner = FakeGitRunner()
    git_runner.fail(
        (
            "git",
            "branch",
            "--create-reflog",
            "prd/1-build-langgraph-agent-orchestration-system",
            "origin/main",
        ),
        "branch setup failed",
    )
    workspace = GitWorkspaceGateway(runner=git_runner)
    service = PrdPreparationService(issues=issue_gateway, workspace=workspace)

    result = service.prepare_issue(
        repo_path="/repos/demo",
        main_branch="main",
        issue_number=1,
    )

    assert result.succeeded is False
    assert result.failure_message == "branch setup failed"
    assert issue_gateway.updated_bodies == []


def test_github_issue_gateway_type_remains_compatible() -> None:
    def accepts_gateway(_: GitHubIssueGateway) -> None:
        return None

    accepts_gateway(GitHubIssueGateway())
