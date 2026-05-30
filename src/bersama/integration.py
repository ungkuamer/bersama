from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol

from bersama.github_issues import GitHubIssueGateway, GitHubIssueRecord
from bersama.issues import GitHubIssue, ImplementationIssue, PrdIssue, parse_issue


class IntegrationError(RuntimeError):
    """Base class for integration workspace errors."""
    pass


class UpdateError(IntegrationError):
    """Raised when updating the implementation branch against the PRD branch fails."""
    pass


class MergeConflictError(UpdateError):
    """Raised when there is a merge conflict during the update."""
    pass


class PushError(IntegrationError):
    """Raised when pushing a branch fails."""
    pass


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
class IntegrationResult:
    issue_number: int
    status: str  # "succeeded" | "failed"
    failure_type: str | None = None  # "merge_conflict" | "update_failure" | "push_failure" | None
    failure_message: str | None = None
    implementation_branch: str | None = None
    prd_branch: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


class IntegrationWorkspaceGateway:
    def __init__(
        self,
        runner: GitRunner = run_git,
        lock: "object | None" = None,
    ) -> None:
        self._runner = runner
        self._lock = lock

    def update_branch(
        self, *, worktree_path: str, implementation_branch: str, prd_branch: str
    ) -> None:
        # 1. Fetch latest refs from remote
        if self._lock:
            self._lock.acquire()
        try:
            self._run(("git", "fetch", "origin"), cwd=worktree_path)

            # 2. Attempt to merge origin/prd_branch into the current local branch
            try:
                self._run(
                    (
                        "git",
                        "merge",
                        f"origin/{prd_branch}",
                        "-m",
                        f"Update implementation branch against latest {prd_branch}",
                    ),
                    cwd=worktree_path,
                )
            except IntegrationError as exc:
                # Clean up the conflicted merge state if possible
                try:
                    self._run(("git", "merge", "--abort"), cwd=worktree_path)
                except Exception:
                    pass
                raise exc
        finally:
            if self._lock:
                self._lock.release()

    def push_branch(self, *, worktree_path: str, branch_name: str) -> None:
        if self._lock:
            self._lock.acquire()
        try:
            self._run(("git", "push", "origin", branch_name), cwd=worktree_path)
        finally:
            if self._lock:
                self._lock.release()

    def merge_into_prd(
        self, *, worktree_path: str, implementation_branch: str, prd_branch: str
    ) -> None:
        if self._lock:
            self._lock.acquire()
        try:
            self._run(
                ("git", "push", "origin", f"{implementation_branch}:{prd_branch}"),
                cwd=worktree_path,
            )
        finally:
            if self._lock:
                self._lock.release()

    def _run(self, command: tuple[str, ...], *, cwd: str) -> str:
        try:
            return self._runner(command, cwd=cwd)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)

            # Determine failure type from context
            cmd_str = " ".join(command)
            if "git merge" in cmd_str:
                if "conflict" in detail.lower() or "merge failed" in detail.lower():
                    raise MergeConflictError(detail) from exc
                raise UpdateError(detail) from exc
            elif "git push" in cmd_str:
                raise PushError(detail) from exc
            
            raise IntegrationError(detail) from exc


class IssueGateway(Protocol):
    def view_issue(self, number: int) -> GitHubIssueRecord: ...
    def add_comment(self, number: int, body: str) -> None: ...
    def add_labels(self, number: int, *labels: str) -> None: ...
    def close_issue(self, number: int) -> None: ...


class IntegrationService:
    def __init__(
        self,
        *,
        issues: IssueGateway,
        workspace: IntegrationWorkspaceGateway,
    ) -> None:
        self._issues = issues
        self._workspace = workspace

    def integrate_issue(
        self,
        *,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
    ) -> IntegrationResult:
        # 1. Fetch and parse the Implementation Issue
        try:
            issue_record = self._issues.view_issue(issue_number)
        except Exception as exc:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Failed to fetch implementation issue: {exc}",
            )

        parsed_issue = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed_issue, ImplementationIssue):
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message="Issue is not an Implementation Issue.",
            )

        parent_prd_number = parsed_issue.parent_prd_number
        if parent_prd_number is None:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message="Implementation Issue is missing parent PRD reference.",
            )

        # 2. Fetch and parse parent PRD Issue to get prd_branch
        try:
            parent_record = self._issues.view_issue(parent_prd_number)
        except Exception as exc:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Failed to fetch parent PRD issue: {exc}",
            )

        parent_issue = parse_issue(
            GitHubIssue(
                number=parent_record.number,
                title=parent_record.title,
                body=parent_record.body,
                labels=parent_record.labels,
            )
        )
        if not isinstance(parent_issue, PrdIssue):
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Parent Issue #{parent_prd_number} is not a PRD Issue.",
            )

        prd_branch = parent_issue.orchestration.prd_branch
        if not prd_branch:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Parent PRD Issue #{parent_prd_number} is missing PRD Branch metadata.",
            )

        # 3. Retrieve claim metadata
        orchestration = parsed_issue.orchestration
        agent_run_id = orchestration.agent_run_id
        implementation_branch = orchestration.implementation_branch
        if not agent_run_id or not implementation_branch:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message="Implementation Issue is not claimed.",
            )

        # 4. Resolve Worktree Path
        worktree_path = str(Path(worktree_root) / f"issue-{issue_number}")
        if not Path(worktree_path).exists():
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Worktree path does not exist: {worktree_path}",
            )

        # 5. Integrate!
        try:
            # 5a. Update implementation branch against latest PRD branch
            self._workspace.update_branch(
                worktree_path=worktree_path,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

            # 5b. Push implementation branch
            self._workspace.push_branch(
                worktree_path=worktree_path,
                branch_name=implementation_branch,
            )

            # 5c. Merge implementation branch into PRD branch
            self._workspace.merge_into_prd(
                worktree_path=worktree_path,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        except MergeConflictError as exc:
            msg = f"Merge conflict while updating implementation branch against PRD branch:\n{exc}"
            self._issues.add_comment(
                issue_number,
                f"Integration failed for implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.\n\n**Diagnostics:**\n{msg}",
            )
            self._issues.add_labels(issue_number, "needs-triage")
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="merge_conflict",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        except UpdateError as exc:
            msg = f"Failed to update implementation branch against PRD branch:\n{exc}"
            self._issues.add_comment(
                issue_number,
                f"Integration failed for implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.\n\n**Diagnostics:**\n{msg}",
            )
            self._issues.add_labels(issue_number, "needs-triage")
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        except PushError as exc:
            msg = f"Push/Merge failure during integration:\n{exc}"
            self._issues.add_comment(
                issue_number,
                f"Integration failed for implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.\n\n**Diagnostics:**\n{msg}",
            )
            self._issues.add_labels(issue_number, "needs-triage")
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="push_failure",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        except IntegrationError as exc:
            msg = f"Integration failed due to an unexpected workspace error:\n{exc}"
            self._issues.add_comment(
                issue_number,
                f"Integration failed for implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.\n\n**Diagnostics:**\n{msg}",
            )
            self._issues.add_labels(issue_number, "needs-triage")
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        # 6. Success! Close silently.
        try:
            self._issues.close_issue(issue_number)
        except Exception as exc:
            # Closing the issue failed, but integration succeeded
            return IntegrationResult(
                issue_number=issue_number,
                status="succeeded",
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                failure_message=f"Integration succeeded, but closing the issue failed: {exc}",
            )

        return IntegrationResult(
            issue_number=issue_number,
            status="succeeded",
            implementation_branch=implementation_branch,
            prd_branch=prd_branch,
        )
