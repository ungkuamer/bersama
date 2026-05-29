from pathlib import Path
from unittest.mock import patch

from bersama.cli import main
from bersama.prd_preparation import PrdPreparationResult


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
