from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from rangkai.command_executor import CommandExecutor

from rangkai.command_executor import CommandError, CommandPhase, CommandResult
from rangkai.command_executor import CommandExecutor


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
            from rangkai.command_executor import CommandError
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

    def _execute_mutation_with_read_back(
        self,
        command: tuple[str, ...],
        *,
        verifier: callable | None = None,
    ) -> str:
        if self._command_executor is None:
            return self._run(command, phase=CommandPhase.LIFECYCLE_MUTATION)

        result = self._command_executor.execute(
            command,
            CommandPhase.LIFECYCLE_MUTATION,
            cwd=str(self._cwd) if self._cwd else None,
        )
        if result.succeeded:
            return result.stdout

        if result.timed_out and verifier is not None:
            try:
                if verifier():
                    return result.stdout
            except CommandError as read_back_exc:
                diagnostics = _combine_diagnostics(
                    result,
                    "Mutation outcome is ambiguous: read-back check failed after timeout.",
                    read_back_exc.result.diagnostics,
                )
                raise CommandError(_replace_diagnostics(result, diagnostics)) from read_back_exc

            diagnostics = _combine_diagnostics(
                result,
                "Mutation outcome is ambiguous: read-back check did not confirm whether the change applied.",
            )
            raise CommandError(_replace_diagnostics(result, diagnostics))

        raise CommandError(result)

    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
        limit: int = 30,
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
            "--limit",
            str(limit),
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

        self._execute_mutation_with_read_back(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--add-label",
                ",".join(labels),
            ),
            verifier=lambda: all(label in self.view_issue(number).labels for label in labels),
        )

    def remove_labels(self, number: int, *labels: str) -> None:
        if not labels:
            return

        self._execute_mutation_with_read_back(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--remove-label",
                ",".join(labels),
            ),
            verifier=lambda: all(label not in self.view_issue(number).labels for label in labels),
        )

    def update_body(self, number: int, body: str) -> None:
        self._execute_mutation_with_read_back(
            (
                "gh",
                "issue",
                "edit",
                str(number),
                "--body",
                body,
            ),
            verifier=lambda: self.view_issue(number).body == body,
        )

    def add_comment(self, number: int, body: str) -> None:
        self._execute_mutation_with_read_back(
            (
                "gh",
                "issue",
                "comment",
                str(number),
                "--body",
                body,
            ),
            verifier=lambda: self._comment_exists(number, body),
        )

    def close_issue(self, number: int) -> None:
        self._execute_mutation_with_read_back(
            ("gh", "issue", "close", str(number)),
            verifier=lambda: self.view_issue(number).state == "closed",
        )

    def _comment_exists(self, number: int, body: str) -> bool:
        output = self._run(
            (
                "gh",
                "issue",
                "view",
                str(number),
                "--json",
                "comments",
            ),
            phase=CommandPhase.DISCOVERY,
        )
        payload = json.loads(output)
        comments_payload = payload.get("comments", [])
        return any(
            isinstance(comment, dict) and str(comment.get("body", "")) == body
            for comment in comments_payload
        )

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


def create_bounded_issue_gateway(*, cwd: str | Path | None = None) -> GitHubIssueGateway:
    return GitHubIssueGateway(
        cwd=cwd,
        command_executor=CommandExecutor(),
    )


def _replace_diagnostics(result: CommandResult, diagnostics: str) -> CommandResult:
    return CommandResult(
        command=result.command,
        phase=result.phase,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        retries_attempted=result.retries_attempted,
        cwd=result.cwd,
        diagnostics=diagnostics,
    )


def _combine_diagnostics(
    result: CommandResult,
    message: str,
    extra: str | None = None,
) -> str:
    parts = [message]
    if result.diagnostics:
        parts.append(result.diagnostics)
    if extra:
        parts.append(f"read-back: {extra}")
    return " ".join(parts)
