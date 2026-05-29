from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bersama.config import AppConfig
from bersama.github_issues import GitHubIssueRecord


class IssueGateway(Protocol):
    def view_issue(self, number: int) -> GitHubIssueRecord: ...


@dataclass(frozen=True)
class ExecutionResult:
    issue_number: int
    status: str  # "succeeded" | "failed"
    exit_code: int
    new_commits: bool
    failure_reason: str | None = None
    log_path: str | None = None
    run_state_path: str | None = None


class HarnessExecutionService:
    def __init__(self, *, issues: IssueGateway) -> None:
        self._issues = issues

    def execute_run(
        self,
        *,
        repo_name: str,
        issue_number: int,
        config: AppConfig,
    ) -> ExecutionResult:
        import os
        import json
        import subprocess
        from datetime import datetime, UTC
        from pathlib import Path
        from bersama.issues import parse_issue, GitHubIssue, ImplementationIssue, PrdIssue

        # 1. Fetch and parse the Implementation Issue
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
            raise ValueError(f"Issue #{issue_number} is not an Implementation Issue.")

        parent_prd_number = parsed_issue.parent_prd_number
        if parent_prd_number is None:
            raise ValueError(f"Implementation Issue #{issue_number} is missing parent PRD reference.")

        # 2. Fetch and parse parent PRD Issue to get prd_branch
        parent_record = self._issues.view_issue(parent_prd_number)
        parent_issue = parse_issue(
            GitHubIssue(
                number=parent_record.number,
                title=parent_record.title,
                body=parent_record.body,
                labels=parent_record.labels,
            )
        )
        if not isinstance(parent_issue, PrdIssue):
            raise ValueError(f"Parent Issue #{parent_prd_number} is not a PRD Issue.")

        prd_branch = parent_issue.orchestration.prd_branch
        if not prd_branch:
            raise ValueError(f"Parent PRD Issue #{parent_prd_number} is not prepared (missing PRD Branch).")

        # 3. Retrieve claim metadata
        orchestration = parsed_issue.orchestration
        agent_run_id = orchestration.agent_run_id
        implementation_branch = orchestration.implementation_branch
        if not agent_run_id or not implementation_branch:
            raise ValueError(f"Implementation Issue #{issue_number} is not claimed.")

        # 4. Resolve Repo and Harness config
        repo = config.repo(repo_name)
        harness = config.harness(repo.default_harness)

        # 5. Resolve Paths and initialized run-state
        worktree_path = Path(repo.worktree_root) / f"issue-{issue_number}"
        if not worktree_path.exists():
            raise FileNotFoundError(f"Worktree path does not exist: {worktree_path}")

        def _utc_now() -> str:
            return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        started_at = _utc_now()
        run_state_path = worktree_path / "run-state.json"
        run_state = {
            "status": "running",
            "issue_number": issue_number,
            "prd_branch": prd_branch,
            "implementation_branch": implementation_branch,
            "started_at": started_at,
        }
        run_state_path.write_text(json.dumps(run_state, indent=2), encoding="utf-8")

        # 6. Render harness command
        format_context = {
            "repo_name": repo.name,
            "repo_path": str(repo.repo_path),
            "main_branch": repo.main_branch,
            "worktree_root": str(repo.worktree_root),
            "global_concurrency": str(repo.global_concurrency),
            "per_prd_concurrency": str(repo.per_prd_concurrency),
            "harness_name": harness.name,
            "issue_number": str(issue_number),
            "parent_prd_number": str(parent_prd_number),
            "prd_branch": prd_branch,
            "implementation_branch": implementation_branch,
        }
        rendered_args = [part.format(**format_context) for part in harness.args_template]
        command = [harness.command] + rendered_args

        # 7. Prepare environments
        env = dict(os.environ)
        env.update({
            "BERSAMA_ISSUE_NUMBER": str(issue_number),
            "BERSAMA_PARENT_PRD_NUMBER": str(parent_prd_number),
            "BERSAMA_PRD_BRANCH": prd_branch,
            "BERSAMA_IMPLEMENTATION_BRANCH": implementation_branch,
            "BERSAMA_REPO_PATH": str(repo.repo_path),
        })

        # 8. Record initial HEAD commit
        def get_head_commit(cwd: Path) -> str:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
            return res.stdout.strip()

        initial_commit = get_head_commit(worktree_path)

        # 9. Run subprocess, capturing stdout/stderr
        log_path = worktree_path / "harness.log"
        with open(log_path, "w", encoding="utf-8") as log_file:
            process = subprocess.run(
                command,
                cwd=worktree_path,
                env=env,
                stdout=log_file,
                stderr=log_file,
            )
        exit_code = process.returncode

        # 10. Record final HEAD commit and verify commit presence
        final_commit = get_head_commit(worktree_path)
        new_commits = initial_commit != final_commit

        # 11. Determine status
        finished_at = _utc_now()
        if exit_code == 0 and new_commits:
            status = "succeeded"
            failure_reason = None
        else:
            status = "failed"
            if exit_code != 0:
                failure_reason = f"Harness exited with non-zero exit code {exit_code}."
            else:
                failure_reason = "Harness exited with code 0 but created no new commits."

        # 12. Update final run-state
        run_state.update({
            "status": status,
            "finished_at": finished_at,
        })
        if failure_reason:
            run_state["failure_reason"] = failure_reason
        run_state_path.write_text(json.dumps(run_state, indent=2), encoding="utf-8")

        return ExecutionResult(
            issue_number=issue_number,
            status=status,
            exit_code=exit_code,
            new_commits=new_commits,
            failure_reason=failure_reason,
            log_path=str(log_path),
            run_state_path=str(run_state_path),
        )
