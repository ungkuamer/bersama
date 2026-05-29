from pathlib import Path
from unittest.mock import patch

from bersama.cli import main
from bersama.claiming import ClaimResult
from bersama.prd_preparation import PrdPreparationResult
from bersama.execution import ExecutionResult


def write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "bersama.yaml"
    config_path.write_text(contents, encoding="utf-8")
    return config_path


def test_run_command_reports_selected_repo(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
    args_template:
      - run
      - --repo
      - "{repo_path}"
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.orchestrator.Orchestrator.run") as mock_run:
        exit_code = main(["run", "demo", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Selected repo: demo" in captured.out
    assert "Command: codex run --repo /repos/demo" in captured.out


def test_invalid_config_exits_without_starting_orchestration(
    capsys, tmp_path: Path
) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    default_harness: local
""".strip(),
    )

    exit_code = main(["run", "demo", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Configuration error:" in captured.err
    assert captured.out == ""


def test_prepare_prd_command_reports_created_branch(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.PrdPreparationService.prepare_issue") as prepare_issue:
        prepare_issue.return_value = PrdPreparationResult(
            issue_number=5,
            prd_branch="prd/5-prepare-prd-issues-with-prd-branches",
            reused_existing_branch=False,
            updated_issue_body=True,
        )

        exit_code = main(
            ["prepare-prd", "demo", "5", "--config", str(config_path)]
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Prepared PRD issue #5" in captured.out
    assert (
        "PRD branch: prd/5-prepare-prd-issues-with-prd-branches (created)"
        in captured.out
    )
    assert "Issue body updated: yes" in captured.out


def test_prepare_prd_command_reports_failures_to_stderr(
    capsys, tmp_path: Path
) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.PrdPreparationService.prepare_issue") as prepare_issue:
        prepare_issue.return_value = PrdPreparationResult(
            issue_number=5,
            prd_branch="prd/5-prepare-prd-issues-with-prd-branches",
            reused_existing_branch=False,
            updated_issue_body=False,
            failure_message="branch setup failed",
        )

        exit_code = main(
            ["prepare-prd", "demo", "5", "--config", str(config_path)]
        )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Failed to prepare PRD issue #5: branch setup failed" in captured.err


def test_claim_issue_command_reports_branch_and_worktree(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.ImplementationClaimService.claim_issue") as claim_issue:
        claim_issue.return_value = ClaimResult(
            issue_number=7,
            agent_run_id="run-123",
            implementation_branch="impl/5/7-claim-implementation-issues",
            worktree_path="/worktrees/demo/issue-7",
        )

        exit_code = main(
            [
                "claim-issue",
                "demo",
                "7",
                "--agent-run-id",
                "run-123",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Claimed implementation issue #7" in captured.out
    assert "Agent run: run-123" in captured.out
    assert "Implementation branch: impl/5/7-claim-implementation-issues" in captured.out
    assert "Worktree: /worktrees/demo/issue-7" in captured.out


def test_claim_issue_command_reports_failures_to_stderr(
    capsys, tmp_path: Path
) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.ImplementationClaimService.claim_issue") as claim_issue:
        claim_issue.return_value = ClaimResult(
            issue_number=7,
            agent_run_id="run-123",
            implementation_branch="impl/5/7-claim-implementation-issues",
            worktree_path=None,
            failure_message="worktree setup failed",
        )

        exit_code = main(
            [
                "claim-issue",
                "demo",
                "7",
                "--agent-run-id",
                "run-123",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        "Failed to claim implementation issue #7: worktree setup failed"
        in captured.err
    )


def test_execute_run_command_success(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.HarnessExecutionService.execute_run") as execute_run:
        execute_run.return_value = ExecutionResult(
            issue_number=8,
            status="succeeded",
            exit_code=0,
            new_commits=True,
            log_path="/worktrees/demo/issue-8/harness.log",
            run_state_path="/worktrees/demo/issue-8/run-state.json",
        )

        exit_code = main(
            [
                "execute-run",
                "demo",
                "8",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Harness execution succeeded for issue #8" in captured.out
    assert "Exit code: 0" in captured.out
    assert "New commit: Yes" in captured.out
    assert "Log path: /worktrees/demo/issue-8/harness.log" in captured.out
    assert "Run state: /worktrees/demo/issue-8/run-state.json" in captured.out


def test_execute_run_command_failure(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.HarnessExecutionService.execute_run") as execute_run:
        execute_run.return_value = ExecutionResult(
            issue_number=8,
            status="failed",
            exit_code=1,
            new_commits=False,
            failure_reason="Harness exited with non-zero exit code 1.",
        )

        exit_code = main(
            [
                "execute-run",
                "demo",
                "8",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Harness execution failed for issue #8: Harness exited with non-zero exit code 1." in captured.err
    assert "Exit code: 1" in captured.err
    assert "New commit: No" in captured.err


def test_integrate_run_command_success(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.IntegrationService.integrate_issue") as integrate_issue:
        from bersama.integration import IntegrationResult
        integrate_issue.return_value = IntegrationResult(
            issue_number=9,
            status="succeeded",
            implementation_branch="impl/1/9-merge-successful-runs",
            prd_branch="prd/1-parent-prd",
        )

        exit_code = main(
            [
                "integrate-run",
                "demo",
                "9",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Successfully integrated issue #9" in captured.out
    assert "Implementation branch: impl/1/9-merge-successful-runs" in captured.out
    assert "PRD branch: prd/1-parent-prd" in captured.out


def test_integrate_run_command_failure(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.IntegrationService.integrate_issue") as integrate_issue:
        from bersama.integration import IntegrationResult
        integrate_issue.return_value = IntegrationResult(
            issue_number=9,
            status="failed",
            failure_type="merge_conflict",
            failure_message="Merge conflict in README.md",
        )

        exit_code = main(
            [
                "integrate-run",
                "demo",
                "9",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Failed to integrate issue #9: Merge conflict in README.md" in captured.err
    assert "Failure type: merge_conflict" in captured.err


def test_reconcile_command_success(capsys, tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with patch("bersama.cli.ReconciliationService.reconcile") as reconcile:
        reconcile.return_value = None

        exit_code = main(
            [
                "reconcile",
                "demo",
                "--config",
                str(config_path),
            ]
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Successfully reconciled issue states for repo: demo" in captured.out
