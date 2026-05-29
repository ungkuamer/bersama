from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Protocol

from bersama.github_issues import GitHubIssueGateway
from bersama.issues import GitHubIssue, PrdIssue, parse_issue, upsert_section


SLUG_RE = re.compile(r"[^a-z0-9]+")


class BranchPreparationError(RuntimeError):
    """Raised when git branch setup fails."""


class GitRunner(Protocol):
    def __call__(self, command: tuple[str, ...], *, cwd: str) -> str: ...


def run_git(command: tuple[str, ...], *, cwd: str) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return completed.stdout


@dataclass(frozen=True)
class PrdPreparationResult:
    issue_number: int
    prd_branch: str | None
    reused_existing_branch: bool
    updated_issue_body: bool
    failure_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure_message is None


class GitWorkspaceGateway:
    def __init__(self, runner: GitRunner = run_git) -> None:
        self._runner = runner

    def ensure_remote_branch(
        self, *, repo_path: str, main_branch: str, branch_name: str
    ) -> bool:
        if self.remote_branch_exists(repo_path=repo_path, branch_name=branch_name):
            return True

        self._run(("git", "fetch", "origin", main_branch), cwd=repo_path)
        self._run(
            ("git", "branch", "--create-reflog", branch_name, f"origin/{main_branch}"),
            cwd=repo_path,
        )
        try:
            self._run(("git", "push", "origin", f"{branch_name}:{branch_name}"), cwd=repo_path)
        except BranchPreparationError:
            self._run(("git", "branch", "-D", branch_name), cwd=repo_path)
            raise
        return False

    def remote_branch_exists(self, *, repo_path: str, branch_name: str) -> bool:
        output = self._run(
            ("git", "ls-remote", "--heads", "origin", branch_name),
            cwd=repo_path,
        )
        return bool(output.strip())

    def _run(self, command: tuple[str, ...], *, cwd: str) -> str:
        try:
            return self._runner(command, cwd=cwd)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise BranchPreparationError(detail) from exc


class PrdPreparationService:
    def __init__(
        self,
        *,
        issues: GitHubIssueGateway,
        workspace: GitWorkspaceGateway,
    ) -> None:
        self._issues = issues
        self._workspace = workspace

    def prepare_issue(
        self, *, repo_path: str, main_branch: str, issue_number: int
    ) -> PrdPreparationResult:
        issue_record = self._issues.view_issue(issue_number)
        parsed = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed, PrdIssue):
            return PrdPreparationResult(
                issue_number=issue_number,
                prd_branch=None,
                reused_existing_branch=False,
                updated_issue_body=False,
                failure_message="Issue is not a PRD Issue.",
            )

        existing_branch = parsed.orchestration.prd_branch
        if existing_branch:
            return PrdPreparationResult(
                issue_number=issue_number,
                prd_branch=existing_branch,
                reused_existing_branch=True,
                updated_issue_body=False,
            )

        branch_name = build_prd_branch_name(issue_number, issue_record.title)
        try:
            reused_existing_branch = self._workspace.ensure_remote_branch(
                repo_path=repo_path,
                main_branch=main_branch,
                branch_name=branch_name,
            )
        except BranchPreparationError as exc:
            return PrdPreparationResult(
                issue_number=issue_number,
                prd_branch=branch_name,
                reused_existing_branch=False,
                updated_issue_body=False,
                failure_message=str(exc),
            )

        updated_body = upsert_prd_branch_metadata(issue_record.body, branch_name)
        self._issues.update_body(issue_number, updated_body)
        return PrdPreparationResult(
            issue_number=issue_number,
            prd_branch=branch_name,
            reused_existing_branch=reused_existing_branch,
            updated_issue_body=True,
        )


def build_prd_branch_name(issue_number: int, title: str) -> str:
    slug = SLUG_RE.sub("-", title.lower()).strip("-")
    if not slug:
        slug = "prd"
    return f"prd/{issue_number}-{slug}"


def upsert_prd_branch_metadata(body: str, branch_name: str) -> str:
    return upsert_section(body, "Orchestration", f"- PRD Branch: {branch_name}")
