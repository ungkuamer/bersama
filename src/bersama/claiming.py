from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
import subprocess
from typing import Protocol

from bersama.github_issues import GitHubIssueGateway
from bersama.issues import GitHubIssue, ImplementationIssue, PrdIssue, parse_issue, upsert_section


SLUG_RE = re.compile(r"[^a-z0-9]+")


class ClaimError(RuntimeError):
    """Raised when claim setup fails."""


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
class ClaimResult:
    issue_number: int
    agent_run_id: str | None
    implementation_branch: str | None
    worktree_path: str | None
    failure_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure_message is None


class ClaimWorkspaceGateway:
    def __init__(
        self,
        runner: GitRunner = run_git,
        lock: "threading.Lock | None" = None,
    ) -> None:
        self._runner = runner
        self._lock = lock

    def ensure_remote_branch_from_base(
        self, *, repo_path: str, base_branch: str, branch_name: str
    ) -> bool:
        if self.remote_branch_exists(repo_path=repo_path, branch_name=branch_name):
            return True

        if self._lock:
            self._lock.acquire()
        try:
            self._run(("git", "fetch", "origin", base_branch), cwd=repo_path)
            self._run(
                ("git", "branch", "--create-reflog", branch_name, f"origin/{base_branch}"),
                cwd=repo_path,
            )
            try:
                self._run(("git", "push", "origin", f"{branch_name}:{branch_name}"), cwd=repo_path)
            except ClaimError:
                self._run(("git", "branch", "-D", branch_name), cwd=repo_path)
                raise
        finally:
            if self._lock:
                self._lock.release()
        return False

    def create_worktree(
        self, *, repo_path: str, worktree_root: str, branch_name: str, issue_number: int
    ) -> str:
        worktree_path = str(Path(worktree_root) / f"issue-{issue_number}")
        self._run(("mkdir", "-p", worktree_root), cwd=repo_path)

        if self._lock:
            self._lock.acquire()
        try:
            # Robustly clean up any stale worktree at this path
            if Path(worktree_path).exists():
                try:
                    self._run(("git", "worktree", "remove", "--force", worktree_path), cwd=repo_path)
                except Exception:
                    import shutil
                    try:
                        shutil.rmtree(worktree_path)
                    except Exception:
                        pass
                try:
                    self._run(("git", "worktree", "prune"), cwd=repo_path)
                except Exception:
                    pass

            self._run(("git", "fetch", "origin", branch_name), cwd=repo_path)
            self._run(
                ("git", "worktree", "add", worktree_path, branch_name),
                cwd=repo_path,
            )
        finally:
            if self._lock:
                self._lock.release()
        return worktree_path

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
            raise ClaimError(detail) from exc


class ImplementationClaimService:
    def __init__(
        self,
        *,
        issues: GitHubIssueGateway,
        workspace: ClaimWorkspaceGateway,
        now_provider: callable | None = None,
    ) -> None:
        self._issues = issues
        self._workspace = workspace
        self._now_provider = now_provider or _utc_now

    def claim_issue(
        self,
        *,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
        agent_run_id: str,
    ) -> ClaimResult:
        issue_record = self._issues.view_issue(issue_number)
        parsed_issue = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed_issue, ImplementationIssue):
            return self._fail(issue_number, "Issue is not an Implementation Issue.")
        if parsed_issue.diagnostics:
            return self._fail(issue_number, "Implementation Issue is missing required metadata.")
        if "ready-for-agent" not in issue_record.labels:
            return self._fail(issue_number, "Implementation Issue is not ready for agent claim.")
        if parsed_issue.orchestration.agent_run_id or parsed_issue.orchestration.claimed_at:
            return self._fail(issue_number, "Implementation Issue is already claimed.")

        assert parsed_issue.parent_prd_number is not None
        parent_record = self._issues.view_issue(parsed_issue.parent_prd_number)
        parent_issue = parse_issue(
            GitHubIssue(
                number=parent_record.number,
                title=parent_record.title,
                body=parent_record.body,
                labels=parent_record.labels,
            )
        )
        if not isinstance(parent_issue, PrdIssue):
            return self._fail(issue_number, "Parent PRD issue is missing or invalid.")
        prd_branch = parent_issue.orchestration.prd_branch
        if not prd_branch:
            return self._fail(issue_number, "Parent PRD issue is not prepared.")

        implementation_branch = build_implementation_branch_name(
            parsed_issue.parent_prd_number,
            issue_number,
            issue_record.title,
        )
        claimed_at = self._now_provider()
        updated_body = upsert_claim_metadata(
            issue_record.body,
            agent_run_id=agent_run_id,
            claimed_at=claimed_at,
            implementation_branch=implementation_branch,
        )

        try:
            self._issues.remove_labels(issue_number, "ready-for-agent")
            self._issues.update_body(issue_number, updated_body)
            self._workspace.ensure_remote_branch_from_base(
                repo_path=repo_path,
                base_branch=prd_branch,
                branch_name=implementation_branch,
            )
            worktree_path = self._workspace.create_worktree(
                repo_path=repo_path,
                worktree_root=worktree_root,
                branch_name=implementation_branch,
                issue_number=issue_number,
            )
        except ClaimError as exc:
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.add_comment(
                issue_number,
                f"Branch setup failed during claim.\n\n**Diagnostics:**\n{exc}"
            )
            return self._fail(issue_number, str(exc), agent_run_id, implementation_branch)

        return ClaimResult(
            issue_number=issue_number,
            agent_run_id=agent_run_id,
            implementation_branch=implementation_branch,
            worktree_path=worktree_path,
        )

    def _fail(
        self,
        issue_number: int,
        message: str,
        agent_run_id: str | None = None,
        implementation_branch: str | None = None,
    ) -> ClaimResult:
        return ClaimResult(
            issue_number=issue_number,
            agent_run_id=agent_run_id,
            implementation_branch=implementation_branch,
            worktree_path=None,
            failure_message=message,
        )


def build_implementation_branch_name(
    prd_issue_number: int, implementation_issue_number: int, title: str
) -> str:
    slug = SLUG_RE.sub("-", title.lower()).strip("-")
    if not slug:
        slug = "implementation"
    return f"impl/{prd_issue_number}/{implementation_issue_number}-{slug}"


def upsert_claim_metadata(
    body: str, *, agent_run_id: str, claimed_at: str, implementation_branch: str
) -> str:
    lines = [
        f"- Agent Run: {agent_run_id}",
        f"- Claimed At: {claimed_at}",
        f"- Implementation Branch: {implementation_branch}",
    ]
    return upsert_section(body, "Orchestration", "\n".join(lines))


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
