import json

from bersama.github_issues import GitHubIssueGateway, GitHubIssueRecord


class FakeRunner:
    def __init__(self, *outputs: str) -> None:
        self._outputs = list(outputs)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...]) -> str:
        self.commands.append(command)
        if not self._outputs:
            return ""
        return self._outputs.pop(0)


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
