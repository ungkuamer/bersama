from pathlib import Path

from bersama.cli import main


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
