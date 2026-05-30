from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Protocol

from bersama.github_issues import GitHubIssueGateway, GitHubIssueRecord
from bersama.issues import (
    GitHubIssue,
    ImplementationIssue,
    PrdIssue,
    parse_issue,
    upsert_section,
)


class IntegrationError(RuntimeError):
    """Base class for integration workspace errors."""
    pass


class UpdateError(IntegrationError):
    """Raised when updating the implementation branch against the PRD branch fails."""
    pass


class MergeConflictError(UpdateError):
    """Raised when there is a merge conflict during the update."""
    pass


class PrCreationError(IntegrationError):
    """Raised when creating a Pull Request via gh pr create fails."""
    pass


class PrMergeError(IntegrationError):
    """Raised when merging a Pull Request via gh pr merge fails."""
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
    status: str  # "succeeded" | "failed" | "pending_validation" | "skipped"
    failure_type: str | None = None  # "merge_conflict" | "update_failure" | "push_failure" | "checks_failed" | None
    failure_message: str | None = None
    implementation_branch: str | None = None
    prd_branch: str | None = None
    pr_number: str | None = None

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

    def create_pr(
        self,
        *,
        worktree_path: str,
        implementation_branch: str,
        prd_branch: str,
        title: str,
        body: str = "",
    ) -> str:
        """Create a Pull Request from implementation_branch into prd_branch.

        Uses ``gh pr create`` and returns the PR number as a string.
        """
        if self._lock:
            self._lock.acquire()
        try:
            cmd: tuple[str, ...] = (
                "gh",
                "pr",
                "create",
                "--head",
                implementation_branch,
                "--base",
                prd_branch,
                "--title",
                title,
                "--body",
                body,
                "--json",
                "number",
                "--jq",
                ".number",
            )
            result = self._run(cmd, cwd=worktree_path)
            return result.strip()
        finally:
            if self._lock:
                self._lock.release()

    def merge_pr(
        self,
        *,
        worktree_path: str,
        pr_number: str,
        merge_option: str = "--squash",
    ) -> str:
        """Merge a Pull Request programmatically.

        Uses ``gh pr merge`` with the configured merge option
        (default: ``--squash``).
        """
        if self._lock:
            self._lock.acquire()
        try:
            cmd: tuple[str, ...] = (
                "gh",
                "pr",
                "merge",
                pr_number,
                merge_option,
            )
            result = self._run(cmd, cwd=worktree_path)
            return result.strip()
        finally:
            if self._lock:
                self._lock.release()

    def check_pr(self, *, worktree_path: str, pr_number: str) -> dict:
        """Check PR status including CI checks.

        Uses ``gh pr view`` returning JSON with state, mergeable, closed,
        and statusCheckRollup fields.
        """
        if self._lock:
            self._lock.acquire()
        try:
            cmd: tuple[str, ...] = (
                "gh",
                "pr",
                "view",
                pr_number,
                "--json",
                "state,mergeable,closed,statusCheckRollup",
            )
            result = self._run(cmd, cwd=worktree_path)
            return json.loads(result)
        finally:
            if self._lock:
                self._lock.release()

    def merge_into_prd(
        self, *, worktree_path: str, implementation_branch: str, prd_branch: str
    ) -> None:
        """Deprecated: use ``create_pr`` + ``merge_pr`` instead.

        Direct branch pushing bypasses PR validation (branch protection,
        CI checks).  Kept for backward compatibility with existing
        callers during the migration window.
        """
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
            elif "gh pr create" in cmd_str:
                raise PrCreationError(detail) from exc
            elif "gh pr merge" in cmd_str:
                raise PrMergeError(detail) from exc

            raise IntegrationError(detail) from exc


class IssueGateway(Protocol):
    def view_issue(self, number: int) -> GitHubIssueRecord: ...
    def add_comment(self, number: int, body: str) -> None: ...
    def add_labels(self, number: int, *labels: str) -> None: ...
    def remove_labels(self, number: int, *labels: str) -> None: ...
    def close_issue(self, number: int) -> None: ...
    def update_body(self, number: int, body: str) -> None: ...


def _all_checks_pass(status_check_rollup: list[dict] | None) -> bool | None:
    """Return True if all checks passed, False if any failed, None if still in progress.

    An empty or missing rollup is treated as all-passing (no checks configured).
    """
    if not status_check_rollup:
        return True
    any_in_progress = False
    for check in status_check_rollup:
        status = check.get("status", "")
        conclusion = check.get("conclusion", "")
        if status == "COMPLETED":
            if conclusion != "SUCCESS":
                return False  # A check completed and failed
        else:
            any_in_progress = True  # QUEUED, IN_PROGRESS, etc.
    if any_in_progress:
        return None  # Still waiting
    return True


def _build_integration_orchestration_body(
    existing_body: str,
    *,
    agent_run_id: str,
    claimed_at: str,
    implementation_branch: str,
    integration_pr: str,
    integration_status: str,
) -> str:
    """Write integration PR metadata into the issue's Orchestration section."""
    lines = [
        f"- Agent Run: {agent_run_id}",
        f"- Claimed At: {claimed_at}",
        f"- Implementation Branch: {implementation_branch}",
        f"- Integration PR: #{integration_pr}",
        f"- Integration Status: {integration_status}",
    ]
    return upsert_section(existing_body, "Orchestration", "\n".join(lines))


class IntegrationService:
    def __init__(
        self,
        *,
        issues: IssueGateway,
        workspace: IntegrationWorkspaceGateway,
    ) -> None:
        self._issues = issues
        self._workspace = workspace

    def create_integration_pr(
        self,
        *,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
    ) -> IntegrationResult:
        """Create an Integration Pull Request for an implementation issue.

        Performs the fast, synchronous part: update branch against PRD,
        push, and create a PR.  Writes ``Integration PR`` and
        ``Integration Status: pending_validation`` into the issue's
        Orchestration section so the async poller can pick it up.

        On failure (merge conflict, update error, PR creation failure)
        the issue is labelled ``needs-triage`` and commented with
        diagnostics.
        """
        # 1. Fetch and validate the implementation issue
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

        orchestration = parsed_issue.orchestration
        agent_run_id = orchestration.agent_run_id
        implementation_branch = orchestration.implementation_branch
        claimed_at = orchestration.claimed_at or ""

        if not agent_run_id or not implementation_branch:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message="Implementation Issue is not claimed.",
            )

        # 2. Fetch parent PRD to get prd_branch
        parent_prd_number = parsed_issue.parent_prd_number
        if parent_prd_number is None:
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message="Implementation Issue is missing parent PRD reference.",
            )

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

        # 3. Resolve worktree path
        worktree_path = str(Path(worktree_root) / f"issue-{issue_number}")
        if not Path(worktree_path).exists():
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Worktree path does not exist: {worktree_path}",
            )

        # 4. Update branch, push, create PR
        pr_number: str | None = None
        try:
            self._workspace.update_branch(
                worktree_path=worktree_path,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

            self._workspace.push_branch(
                worktree_path=worktree_path,
                branch_name=implementation_branch,
            )

            pr_number = self._workspace.create_pr(
                worktree_path=worktree_path,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                title=f"Integration: #{issue_number} into {prd_branch}",
                body=f"Automated integration of implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.",
            )

        except MergeConflictError as exc:
            msg = f"Merge conflict while updating implementation branch against PRD branch:\n{exc}"
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.update_body(
                issue_number,
                _build_integration_orchestration_body(
                    issue_record.body,
                    agent_run_id=agent_run_id,
                    claimed_at=claimed_at,
                    implementation_branch=implementation_branch,
                    integration_pr="N/A",
                    integration_status="conflict",
                ),
            )
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="merge_conflict",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        except (UpdateError, PushError, PrCreationError, IntegrationError) as exc:
            msg = f"Integration PR creation failed:\n{exc}"
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.update_body(
                issue_number,
                _build_integration_orchestration_body(
                    issue_record.body,
                    agent_run_id=agent_run_id,
                    claimed_at=claimed_at,
                    implementation_branch=implementation_branch,
                    integration_pr="N/A",
                    integration_status="failed",
                ),
            )
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type=_exc_to_failure_type(exc),
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
            )

        # 5. Success! Write pending_validation orchestration
        self._issues.update_body(
            issue_number,
            _build_integration_orchestration_body(
                issue_record.body,
                agent_run_id=agent_run_id,
                claimed_at=claimed_at,
                implementation_branch=implementation_branch,
                integration_pr=pr_number,
                integration_status="pending_validation",
            ),
        )

        return IntegrationResult(
            issue_number=issue_number,
            status="pending_validation",
            implementation_branch=implementation_branch,
            prd_branch=prd_branch,
            pr_number=pr_number,
        )

    def poll_integration_pr(
        self,
        *,
        repo_path: str,
        worktree_root: str,
        issue_number: int,
    ) -> IntegrationResult:
        """Poll an Integration PR's status checks and merge if green.

        Reads the issue's Orchestration section for ``Integration PR``
        and ``Integration Status``.  Only acts when the status is
        ``pending_validation``.

        * If all CI checks pass → merge PR, close issue.
        * If checks fail → label ``needs-triage``, write ``failed`` status.
        * If PR has merge conflict → label ``needs-triage``, write ``conflict``.
        * If PR was already merged externally → close issue.
        """
        # 1. Fetch and parse the implementation issue
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

        orchestration = parsed_issue.orchestration
        integration_pr = orchestration.integration_pr
        integration_status = orchestration.integration_status
        implementation_branch = orchestration.implementation_branch or ""
        prd_branch = ""

        # Only poll issues in pending_validation state with a PR number
        if integration_status != "pending_validation" or not integration_pr or integration_pr == "N/A":
            return IntegrationResult(
                issue_number=issue_number,
                status="skipped",
                implementation_branch=orchestration.implementation_branch,
                pr_number=integration_pr,
            )

        # 2. Resolve worktree path
        worktree_path = str(Path(worktree_root) / f"issue-{issue_number}")
        if not Path(worktree_path).exists():
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=f"Worktree path does not exist: {worktree_path}",
            )

        # Get PRD branch from parent for diagnostics
        parent_prd_number = parsed_issue.parent_prd_number
        if parent_prd_number is not None:
            try:
                parent_record = self._issues.view_issue(parent_prd_number)
                parent_issue = parse_issue(
                    GitHubIssue(
                        number=parent_record.number,
                        title=parent_record.title,
                        body=parent_record.body,
                        labels=parent_record.labels,
                    )
                )
                if isinstance(parent_issue, PrdIssue):
                    prd_branch = parent_issue.orchestration.prd_branch or ""
            except Exception:
                pass

        # 3. Check PR status
        try:
            pr_status = self._workspace.check_pr(
                worktree_path=worktree_path,
                pr_number=integration_pr,
            )
        except Exception as exc:
            # If we can't check PR status (e.g. PR deleted), mark as failed
            msg = f"Failed to check PR #{integration_pr} status:\n{exc}"
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="update_failure",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )

        # 4. Handle PR state
        pr_state = pr_status.get("state", "").upper()
        pr_closed = pr_status.get("closed", False)
        pr_mergeable = pr_status.get("mergeable", "").upper()

        # Already merged (externally or by a previous poll)
        if pr_state == "MERGED" or (pr_closed and pr_state != "OPEN"):
            try:
                self._issues.close_issue(issue_number)
            except Exception:
                pass
            return IntegrationResult(
                issue_number=issue_number,
                status="succeeded",
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )

        # PR has merge conflict
        if pr_mergeable == "CONFLICTING":
            msg = f"Integration PR #{integration_pr} has a merge conflict."
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.update_body(
                issue_number,
                _build_integration_orchestration_body(
                    issue_record.body,
                    agent_run_id=orchestration.agent_run_id or "",
                    claimed_at=orchestration.claimed_at or "",
                    implementation_branch=implementation_branch,
                    integration_pr=integration_pr,
                    integration_status="conflict",
                ),
            )
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="merge_conflict",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )

        # Check CI status
        status_checks = pr_status.get("statusCheckRollup", [])
        checks_result = _all_checks_pass(status_checks)
        if checks_result is None:
            # Checks still in progress — skip this cycle, try again later
            return IntegrationResult(
                issue_number=issue_number,
                status="skipped",
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )
        if checks_result is False:
            msg = f"Integration PR #{integration_pr} CI/CD checks failed."
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.update_body(
                issue_number,
                _build_integration_orchestration_body(
                    issue_record.body,
                    agent_run_id=orchestration.agent_run_id or "",
                    claimed_at=orchestration.claimed_at or "",
                    implementation_branch=implementation_branch,
                    integration_pr=integration_pr,
                    integration_status="failed",
                ),
            )
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="checks_failed",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )

        # 5. All checks pass — merge!
        try:
            self._workspace.merge_pr(
                worktree_path=worktree_path,
                pr_number=integration_pr,
            )
        except PrMergeError as exc:
            msg = f"PR merge failed for #{integration_pr}:\n{exc}"
            self._issues.add_comment(issue_number, _integration_diag_comment(msg, implementation_branch, prd_branch))
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.update_body(
                issue_number,
                _build_integration_orchestration_body(
                    issue_record.body,
                    agent_run_id=orchestration.agent_run_id or "",
                    claimed_at=orchestration.claimed_at or "",
                    implementation_branch=implementation_branch,
                    integration_pr=integration_pr,
                    integration_status="failed",
                ),
            )
            return IntegrationResult(
                issue_number=issue_number,
                status="failed",
                failure_type="checks_failed",
                failure_message=msg,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                pr_number=integration_pr,
            )

        # 6. Merge succeeded — close the issue
        try:
            self._issues.close_issue(issue_number)
        except Exception:
            pass

        return IntegrationResult(
            issue_number=issue_number,
            status="succeeded",
            implementation_branch=implementation_branch,
            prd_branch=prd_branch,
            pr_number=integration_pr,
        )

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

            # 5c. Create PR from implementation branch into PRD branch
            pr_number = self._workspace.create_pr(
                worktree_path=worktree_path,
                implementation_branch=implementation_branch,
                prd_branch=prd_branch,
                title=f"Integration: #{issue_number} into {prd_branch}",
                body=f"Automated integration of implementation branch `{implementation_branch}` into PRD branch `{prd_branch}`.",
            )

            # 5d. Merge the PR
            self._workspace.merge_pr(
                worktree_path=worktree_path,
                pr_number=pr_number,
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

        except PrCreationError as exc:
            msg = f"PR creation failure during integration:\n{exc}"
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

        except PrMergeError as exc:
            msg = f"PR merge failure during integration:\n{exc}"
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


def _integration_diag_comment(
    message: str,
    implementation_branch: str,
    prd_branch: str,
) -> str:
    """Format a diagnostic comment for integration failures."""
    return (
        f"Integration failed for implementation branch `{implementation_branch}`"
        f" into PRD branch `{prd_branch}`.\n\n"
        f"**Diagnostics:**\n{message}"
    )


def _exc_to_failure_type(exc: Exception) -> str:
    """Map an exception to a failure_type string."""
    if isinstance(exc, MergeConflictError):
        return "merge_conflict"
    if isinstance(exc, UpdateError):
        return "update_failure"
    if isinstance(exc, (PushError, PrCreationError, PrMergeError)):
        return "push_failure"
    return "update_failure"
