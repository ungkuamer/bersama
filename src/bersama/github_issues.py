from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from bersama.command_executor import CommandExecutor

from bersama.command_executor import CommandPhase


@dataclass(frozen=True)
class GitHubIssueRecord:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str


class CommandRunner(Protocol):
    def __call__(self, command: tuple[str, ...], *, cwd: str | Path | None = None) -> str: ...


def run_subprocess(command: tuple[str, ...], *, cwd: str | Path | None = None) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return completed.stdout


class GitHubIssueGateway:
    def __init__(
        self,
        runner: CommandRunner = run_subprocess,
        *,
        cwd: str | Path | None = None,
        command_executor: CommandExecutor | None = None,
    ) -> None:
        self._runner = runner
        self._cwd = cwd
        self._command_executor = command_executor

    def _run(
        self,
        command: tuple[str, ...],
        *,
        phase: CommandPhase | None = None,
    ) -> str:
        if self._command_executor is not None and phase is not None:
            from bersama.command_executor import CommandError
            result = self._command_executor.execute(command, phase, cwd=str(self._cwd) if self._cwd else None)
            if not result.succeeded:
                raise CommandError(result)
            return result.stdout
        if self._cwd is not None:
            try:
                return self._runner(command, cwd=self._cwd)
            except TypeError:
                return self._runner(command)
        return self._runner(command)

    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
    ) -> tuple[GitHubIssueRecord, ...]:
        if label is not None and labels is not None:
            raise ValueError(
                "Cannot specify both 'label' and 'labels'; use 'labels' for OR-based multi-label filtering."
            )

        command = [
            "gh",
            "issue",
            "list",
            "--state",
            state,
            "--json",
            "number,title,body,labels,state",
        ]

        search_terms: list[str] = []
        if labels is not None:
            search_terms.append(f"label:{','.join(labels)}")
        if updated_since is not None:
            search_terms.append(f"updated:>={updated_since}")
        if search_terms:
            command.extend(["--search", " ".join(search_terms)])

        if label is not None:
            command.extend(["--label", label])

        output = self._run(tuple(command), phase=CommandPhase.DISCOVERY)
        return self._parse_issue_records(output)

    def view_issue(self, number: int) -> GitHubIssueRecord:
        output = self._run(
            (
                "gh",
                "issue",
                "view",
                str(number),
                "--json",
                "number,title,body,labels,state",
            ),
            phase=CommandPhase.DISCOVERY,
        )
        return self._parse_issue_record(json.loads(output))

    def add_labels(self, number: int, *labels: str) -> None:
        if not labels:
            return

        try:
            self._run(
                (
                    "gh",
                    "issue",
                    "edit",
                    str(number),
                    "--add-label",
                    ",".join(labels),
                ),
                phase=CommandPhase.LIFECYCLE_MUTATION,
            )
        except Exception as exc:
            import sys
            # Attempt to create any missing labels, then retry
            for label in labels:
                try:
                    self._run(("gh", "label", "create", label, "--color", "ededed"), phase=CommandPhase.LIFECYCLE_MUTATION)
                except Exception:
                    pass
            try:
                self._run(
                    (
                        "gh",
                        "issue",
                        "edit",
                        str(number),
                        "--add-label",
                        ",".join(labels),
                    ),
                    phase=CommandPhase.LIFECYCLE_MUTATION,
                )
            except Exception as retry_exc:
                print(f"Warning: Failed to add labels {labels} to issue #{number}: {retry_exc}", file=sys.stderr)

    def remove_labels(self, number: int, *labels: str) -> None:
        if not labels:
            return

        try:
            self._run(
                (
                    "gh",
                    "issue",
                    "edit",
                    str(number),
                    "--remove-label",
                    ",".join(labels),
                ),
                phase=CommandPhase.LIFECYCLE_MUTATION,
            )
        except Exception as exc:
            import sys
            print(f"Warning: Failed to remove labels {labels} from issue #{number}: {exc}", file=sys.stderr)

    def update_body(self, number: int, body: str) -> None:
        self._run(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--body",
                body,
            ),
            phase=CommandPhase.LIFECYCLE_MUTATION,
        )

    def add_comment(self, number: int, body: str) -> None:
        self._run(
            (
                "gh",
                "issue",
                "comment",
                str(number),
                "--body",
                body,
            ),
            phase=CommandPhase.LIFECYCLE_MUTATION,
        )

    def close_issue(self, number: int) -> None:
        self._run(("gh", "issue", "close", str(number)), phase=CommandPhase.LIFECYCLE_MUTATION)

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
