from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Protocol


@dataclass(frozen=True)
class GitHubIssueRecord:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str


class CommandRunner(Protocol):
    def __call__(self, command: tuple[str, ...]) -> str: ...


def run_subprocess(command: tuple[str, ...]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


class GitHubIssueGateway:
    def __init__(self, runner: CommandRunner = run_subprocess) -> None:
        self._runner = runner

    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
    ) -> tuple[GitHubIssueRecord, ...]:
        command = [
            "gh",
            "issue",
            "list",
            "--state",
            state,
            "--json",
            "number,title,body,labels,state",
        ]
        if label is not None:
            command.extend(["--label", label])

        output = self._runner(tuple(command))
        return self._parse_issue_records(output)

    def view_issue(self, number: int) -> GitHubIssueRecord:
        output = self._runner(
            (
                "gh",
                "issue",
                "view",
                str(number),
                "--json",
                "number,title,body,labels,state",
            )
        )
        return self._parse_issue_record(json.loads(output))

    def add_labels(self, number: int, *labels: str) -> None:
        if not labels:
            return

        self._runner(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--add-label",
                ",".join(labels),
            )
        )

    def remove_labels(self, number: int, *labels: str) -> None:
        if not labels:
            return

        self._runner(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--remove-label",
                ",".join(labels),
            )
        )

    def update_body(self, number: int, body: str) -> None:
        self._runner(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--body",
                body,
            )
        )

    def add_comment(self, number: int, body: str) -> None:
        self._runner(
            (
                "gh",
                "issue",
                "comment",
                str(number),
                "--body",
                body,
            )
        )

    def close_issue(self, number: int) -> None:
        self._runner(("gh", "issue", "close", str(number)))

    def _parse_issue_records(self, output: str) -> tuple[GitHubIssueRecord, ...]:
        payload = json.loads(output)
        return tuple(self._parse_issue_record(item) for item in payload)

    def _parse_issue_record(self, payload: dict[str, object]) -> GitHubIssueRecord:
        labels_payload = payload.get("labels", [])
        labels = tuple(
            label["name"]
            for label in labels_payload
            if isinstance(label, dict) and isinstance(label.get("name"), str)
        )
        return GitHubIssueRecord(
            number=int(payload["number"]),
            title=str(payload["title"]),
            body=str(payload["body"]),
            labels=labels,
            state=str(payload["state"]).lower(),
        )
