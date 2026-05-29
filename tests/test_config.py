from pathlib import Path

import pytest

from bersama.config import ConfigError, load_config


def write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "bersama.yaml"
    config_path.write_text(contents, encoding="utf-8")
    return config_path


def test_loads_valid_config(tmp_path: Path) -> None:
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
    global_concurrency: 3
    per_prd_concurrency: 2
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)

    repo = config.repos["demo"]
    harness = config.harnesses["local"]
    assert repo.repo_path == Path("/repos/demo")
    assert repo.global_concurrency == 3
    assert repo.per_prd_concurrency == 2
    assert harness.command == "codex"
    assert harness.args_template == ("run", "--repo", "{repo_path}")


def test_missing_required_repo_field_raises_clear_error(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with pytest.raises(ConfigError, match="repo 'demo' must define non-empty 'repo_path'"):
        load_config(config_path)


def test_unknown_harness_reference_raises_error(tmp_path: Path) -> None:
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
    default_harness: missing
""".strip(),
    )

    with pytest.raises(ConfigError, match="references unknown harness 'missing'"):
        load_config(config_path)


def test_repo_concurrency_defaults_are_applied(tmp_path: Path) -> None:
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

    config = load_config(config_path)

    repo = config.repos["demo"]
    assert repo.global_concurrency == 1
    assert repo.per_prd_concurrency == 1


def test_harness_command_template_is_loaded(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
    args_template:
      - run
      - --branch
      - "{main_branch}"
repos:
  demo:
    repo_path: /repos/demo
    main_branch: trunk
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)
    harness = config.harnesses["local"]

    assert harness.args_template == ("run", "--branch", "{main_branch}")
