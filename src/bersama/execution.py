from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bersama.config import AppConfig
from bersama.github_issues import GitHubIssueRecord


class IssueGateway(Protocol):
    def view_issue(self, number: int) -> GitHubIssueRecord: ...
    def add_comment(self, number: int, body: str) -> None: ...
    def add_labels(self, number: int, *labels: str) -> None: ...
    def remove_labels(self, number: int, *labels: str) -> None: ...


@dataclass(frozen=True)
class ExecutionResult:
    issue_number: int
    status: str  # "succeeded" | "failed"
    exit_code: int
    new_commits: bool
    failure_reason: str | None = None
    log_path: str | None = None
    run_state_path: str | None = None


def extract_last_agent_message(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    try:
        content = log_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        message_lines = []
        in_codex_block = False
        for line in lines:
            stripped = line.strip()
            if stripped == "codex":
                message_lines = []
                in_codex_block = True
            elif in_codex_block:
                if stripped in ("exec", "user", "OpenAI Codex", "workdir:", "session id:", "--------"):
                    in_codex_block = False
                else:
                    message_lines.append(line)
        
        if message_lines:
            return "\n".join(message_lines).strip()
    except Exception:
        pass
    return None


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
        import signal
        import json
        import subprocess
        from datetime import datetime, UTC
        from pathlib import Path
        from bersama.issues import parse_issue, GitHubIssue, ImplementationIssue, PrdIssue

        try:
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

            # 9. Run subprocess with process group and timeout, capturing stdout/stderr
            log_path = worktree_path / "harness.log"
            timeout_expired = False
            with open(log_path, "w", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    cwd=worktree_path,
                    env=env,
                    stdout=log_file,
                    stderr=log_file,
                    preexec_fn=os.setsid,
                )
                try:
                    process.wait(timeout=harness.timeout_seconds)
                    exit_code = process.returncode
                except subprocess.TimeoutExpired:
                    timeout_expired = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    exit_code = -1

            # 10. Record final HEAD commit and verify commit presence
            final_commit = get_head_commit(worktree_path)
            new_commits = initial_commit != final_commit

            # 11. Determine status
            finished_at = _utc_now()
            if exit_code == 0 and new_commits:
                status = "succeeded"
                failure_reason = None
            else:
                agent_msg = None
                if exit_code == 0 and not new_commits:
                    agent_msg = extract_last_agent_message(log_path)

                if agent_msg:
                    status = "paused"
                    failure_reason = None
                    self._issues.add_labels(issue_number, "needs-info")
                    self._issues.add_comment(
                        issue_number,
                        f"🤖 **Agent Question / Clarification:**\n\n{agent_msg}\n\n"
                        f"*(Please reply with your answers/confirmations and mark this issue as `ready-for-agent` to resume the run.)*"
                    )
                else:
                    status = "failed"
                    if timeout_expired:
                        failure_reason = f"Harness execution timed out after {harness.timeout_seconds} seconds."
                    elif exit_code != 0:
                        failure_reason = f"Harness exited with non-zero exit code {exit_code}."
                    else:
                        failure_reason = "Harness exited with code 0 but created no new commits."

                    self._issues.add_labels(issue_number, "needs-triage")
                    self._issues.add_comment(
                        issue_number,
                        f"Harness execution failed.\n\n**Diagnostics:**\n{failure_reason}"
                    )

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
        except Exception as exc:
            self._issues.add_labels(issue_number, "needs-triage")
            self._issues.add_comment(
                issue_number,
                f"Harness execution failed during setup or execution.\n\n**Diagnostics:**\n{exc}"
            )
            return ExecutionResult(
                issue_number=issue_number,
                status="failed",
                exit_code=-1,
                new_commits=False,
                failure_reason=f"Harness execution failed during setup or execution: {exc}",
            )
