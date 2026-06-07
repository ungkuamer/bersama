import json

import pytest

from rangkai.command_executor import CommandError, CommandPhase, CommandResult
from rangkai.github_issues import GitHubIssueGateway, GitHubIssueRecord


class FakeRunner:
    def __init__(self, *outputs: str) -> None:
        self._outputs = list(outputs)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...]) -> str:
        self.commands.append(command)
        if not self._outputs:
            return ""
        return self._outputs.pop(0)


class StubExecutor:
    def __init__(self, *results: CommandResult) -> None:
        self._results = list(results)
        self.calls: list[tuple[tuple[str, ...], CommandPhase]] = []

    def execute(
        self,
        command: tuple[str, ...],
        phase: CommandPhase,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        retry_safety_check=None,
    ) -> CommandResult:
        del cwd, timeout, retries
        self.calls.append((command, phase))
        result = self._results.pop(0)
        if retry_safety_check is not None and not result.succeeded:
            retry_safety_check(result)
        return result


def _command_result(
    *,
    command: tuple[str, ...],
    phase: CommandPhase,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    timed_out: bool = False,
    retries_attempted: int = 0,
    diagnostics: str | None = None,
) -> CommandResult:
    return CommandResult(
        command=command,
        phase=phase,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        retries_attempted=retries_attempted,
        diagnostics=diagnostics,
        cwd=None,
    )


def test_list_issues_returns_open_and_closed_issue_records() -> None:
    runner = FakeRunner(
        json.dumps(
            [
                {
                    "number": 1,
                    "title": "PRD",
                    "body": "Plan work",
                    "labels": [{"name": "prd"}],
                    "state": "OPEN",
                },
                {
                    "number": 2,
                    "title": "Implementation",
                    "body": "Ship code",
                    "labels": [{"name": "implementation"}, {"name": "ready-for-agent"}],
                    "state": "CLOSED",
                },
            ]
        )
    )

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(state="all")

    assert issues == (
        GitHubIssueRecord(
            number=1,
            title="PRD",
            body="Plan work",
            labels=("prd",),
            state="open",
        ),
        GitHubIssueRecord(
            number=2,
            title="Implementation",
            body="Ship code",
            labels=("implementation", "ready-for-agent"),
            state="closed",
        ),
    )
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
        )
    ]


def test_list_issues_can_filter_by_label() -> None:
    runner = FakeRunner("[]")

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(state="open", label="implementation")

    assert issues == ()
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
            "--label",
            "implementation",
        )
    ]


def test_view_issue_returns_single_issue_record() -> None:
    runner = FakeRunner(
        json.dumps(
            {
                "number": 4,
                "title": "Gateway",
                "body": "Build a gh gateway",
                "labels": [{"name": "implementation"}],
                "state": "OPEN",
            }
        )
    )

    gateway = GitHubIssueGateway(runner=runner)

    issue = gateway.view_issue(4)

    assert issue == GitHubIssueRecord(
        number=4,
        title="Gateway",
        body="Build a gh gateway",
        labels=("implementation",),
        state="open",
    )
    assert runner.commands == [
        (
            "gh",
            "issue",
            "view",
            "4",
            "--json",
            "number,title,body,labels,state",
        )
    ]


def test_add_and_remove_labels_edit_issue_lifecycle_state() -> None:
    runner = FakeRunner("", "")

    gateway = GitHubIssueGateway(runner=runner)

    gateway.add_labels(4, "ready-for-agent", "implementation")
    gateway.remove_labels(4, "needs-triage")

    assert runner.commands == [
        (
            "gh",
            "issue",
            "edit",
            "4",
            "--add-label",
            "ready-for-agent,implementation",
        ),
        (
            "gh",
            "issue",
            "edit",
            "4",
            "--remove-label",
            "needs-triage",
        ),
    ]


def test_update_body_records_orchestration_metadata() -> None:
    runner = FakeRunner("")

    gateway = GitHubIssueGateway(runner=runner)

    gateway.update_body(4, "## Orchestration\n- Agent Run: run-123")

    assert runner.commands == [
        (
            "gh",
            "issue",
            "edit",
            "4",
            "--body",
            "## Orchestration\n- Agent Run: run-123",
        )
    ]


def test_add_comment_posts_diagnostic_message() -> None:
    runner = FakeRunner("")

    gateway = GitHubIssueGateway(runner=runner)

    gateway.add_comment(4, "Missing Parent PRD section.")

    assert runner.commands == [
        (
            "gh",
            "issue",
            "comment",
            "4",
            "--body",
            "Missing Parent PRD section.",
        )
    ]


def test_close_issue_does_not_add_success_comment() -> None:
    runner = FakeRunner("")

    gateway = GitHubIssueGateway(runner=runner)

    gateway.close_issue(4)

    assert runner.commands == [("gh", "issue", "close", "4")]


def test_list_issues_filters_by_multiple_labels_using_search() -> None:
    """When labels tuple is provided, issues are filtered by OR'd labels via --search."""
    runner = FakeRunner("[]")

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(state="all", labels=("prd", "implementation"))

    assert issues == ()
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
            "--search",
            "label:prd,implementation",
        )
    ]


def test_list_issues_filters_by_single_label_in_labels_tuple() -> None:
    """Single-element labels tuple still uses --search for consistency."""
    runner = FakeRunner("[]")

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(state="open", labels=("prd",))

    assert issues == ()
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
            "--search",
            "label:prd",
        )
    ]


def test_list_issues_filters_by_updated_since_date() -> None:
    """updated_since adds an updated:>= filter via --search."""
    runner = FakeRunner("[]")

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(state="closed", updated_since="2026-05-29")

    assert issues == ()
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "closed",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
            "--search",
            "updated:>=2026-05-29",
        )
    ]


def test_list_issues_combines_labels_and_updated_since_in_search() -> None:
    """Both labels and updated_since are combined into a single --search query."""
    runner = FakeRunner("[]")

    gateway = GitHubIssueGateway(runner=runner)

    issues = gateway.list_issues(
        state="all", labels=("prd", "implementation"), updated_since="2026-05-29"
    )

    assert issues == ()
    assert runner.commands == [
        (
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels,state",
            "--search",
            "label:prd,implementation updated:>=2026-05-29",
        )
    ]


def test_list_issues_labels_and_single_label_are_mutually_exclusive() -> None:
    """Passing both label and labels raises ValueError."""
    runner = FakeRunner()
    gateway = GitHubIssueGateway(runner=runner)

    raised = False
    try:
        gateway.list_issues(state="open", label="prd", labels=("implementation",))
    except ValueError:
        raised = True

    assert raised, "Expected ValueError when both label and labels are provided"


def test_discovery_timeout_raises_without_mutation_fallback() -> None:
    command = (
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--limit",
        "30",
        "--json",
        "number,title,body,labels,state",
    )
    executor = StubExecutor(
        _command_result(
            command=command,
            phase=CommandPhase.DISCOVERY,
            timed_out=True,
            exit_code=-1,
            diagnostics="Command timed out after 30s",
        )
    )
    gateway = GitHubIssueGateway(command_executor=executor)

    with pytest.raises(CommandError):
        gateway.list_issues()

    assert executor.calls == [(command, CommandPhase.DISCOVERY)]


def test_mutation_timeout_with_read_back_success_treats_add_labels_as_succeeded() -> None:
    mutation_command = ("gh", "issue", "edit", "4", "--add-label", "ready-for-agent")
    read_back_command = (
        "gh",
        "issue",
        "view",
        "4",
        "--json",
        "number,title,body,labels,state",
    )
    executor = StubExecutor(
        _command_result(
            command=mutation_command,
            phase=CommandPhase.LIFECYCLE_MUTATION,
            timed_out=True,
            exit_code=-1,
            diagnostics="Command timed out after 120s",
        ),
        _command_result(
            command=read_back_command,
            phase=CommandPhase.DISCOVERY,
            stdout=json.dumps(
                {
                    "number": 4,
                    "title": "Implementation",
                    "body": "Ship code",
                    "labels": [{"name": "ready-for-agent"}],
                    "state": "OPEN",
                }
            ),
        ),
    )
    gateway = GitHubIssueGateway(command_executor=executor)

    gateway.add_labels(4, "ready-for-agent")

    assert executor.calls == [
        (mutation_command, CommandPhase.LIFECYCLE_MUTATION),
        (read_back_command, CommandPhase.DISCOVERY),
    ]


def test_mutation_timeout_with_read_back_failure_surfaces_ambiguity_diagnostics() -> None:
    mutation_command = (
        "gh",
        "issue",
        "edit",
        "4",
        "--body",
        "## Orchestration\n- Agent Run: run-123",
    )
    read_back_command = (
        "gh",
        "issue",
        "view",
        "4",
        "--json",
        "number,title,body,labels,state",
    )
    executor = StubExecutor(
        _command_result(
            command=mutation_command,
            phase=CommandPhase.LIFECYCLE_MUTATION,
            timed_out=True,
            exit_code=-1,
            diagnostics="Command timed out after 120s",
        ),
        _command_result(
            command=read_back_command,
            phase=CommandPhase.DISCOVERY,
            timed_out=True,
            exit_code=-1,
            diagnostics="Command timed out after 30s",
        ),
    )
    gateway = GitHubIssueGateway(command_executor=executor)

    with pytest.raises(CommandError) as excinfo:
        gateway.update_body(4, "## Orchestration\n- Agent Run: run-123")

    assert "ambiguous" in str(excinfo.value).lower()
    assert "read-back" in str(excinfo.value).lower()
    assert executor.calls == [
        (mutation_command, CommandPhase.LIFECYCLE_MUTATION),
        (read_back_command, CommandPhase.DISCOVERY),
    ]


def test_non_retryable_mutation_failure_raises_without_read_back() -> None:
    command = ("gh", "issue", "close", "4")
    executor = StubExecutor(
        _command_result(
            command=command,
            phase=CommandPhase.LIFECYCLE_MUTATION,
            exit_code=1,
            stderr="permission denied",
            diagnostics="Command exited with code 1; stderr: permission denied",
        )
    )
    gateway = GitHubIssueGateway(command_executor=executor)

    with pytest.raises(CommandError) as excinfo:
        gateway.close_issue(4)

    assert "exit_code=1" in str(excinfo.value)
    assert executor.calls == [(command, CommandPhase.LIFECYCLE_MUTATION)]
