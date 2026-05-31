from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bersama.config import AppConfig, HarnessConfig, RepoConfig
from bersama.scheduling_readiness import SchedulingReadinessProvider


def build_config(*, repo_path: Path, worktree_root: Path, default_harness: str = "local") -> AppConfig:
    return AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=repo_path,
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness=default_harness,
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
    )


def test_provider_reports_missing_required_labels_as_one_critical_failure(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    provider = SchedulingReadinessProvider(build_config(repo_path=repo_path, worktree_root=worktree_root))

    with (
        patch("bersama.scheduling_readiness.shutil.which", return_value="/usr/bin/gh"),
        patch("bersama.scheduling_readiness.os.access", return_value=True),
        patch("bersama.scheduling_readiness._run_command") as run_command,
    ):
        run_command.side_effect = [
            _completed(stdout="WRITE"),
            _completed(stdout="implementation\nready-for-agent\n"),
            _completed(stdout=""),
            _completed(),
            _completed(stdout='{"name":"demo"}'),
        ]

        snapshot = provider.build_snapshot("demo")

    checks = snapshot["snapshot"]["readiness_checks"]["critical_failures"]
    assert checks == [
        {
            "message": "Required repository labels are missing.",
            "remediation": "Add the required labels in GitHub before running scheduling.",
            "details": {
                "code": "missing-required-labels",
                "missing_labels": [
                    "claimed",
                    "needs-info",
                    "needs-triage",
                    "prd",
                    "ready-for-human",
                    "wontfix",
                ],
            },
        }
    ]
    assert snapshot["snapshot"]["readiness_checks"]["warnings"] == []


def test_provider_reports_dirty_working_tree_as_warning_not_critical_failure(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    provider = SchedulingReadinessProvider(build_config(repo_path=repo_path, worktree_root=worktree_root))

    with (
        patch("bersama.scheduling_readiness.shutil.which", return_value="/usr/bin/gh"),
        patch("bersama.scheduling_readiness.os.access", return_value=True),
        patch("bersama.scheduling_readiness._run_command") as run_command,
    ):
        run_command.side_effect = [
            _completed(stdout="WRITE"),
            _completed(stdout="\n".join(
                [
                    "prd",
                    "implementation",
                    "ready-for-agent",
                    "claimed",
                    "needs-info",
                    "needs-triage",
                    "ready-for-human",
                    "wontfix",
                ]
            )),
            _completed(stdout=" M src/bersama/dashboard.py\n"),
            _completed(),
            _completed(stdout='{"name":"demo"}'),
        ]

        snapshot = provider.build_snapshot("demo")

    assert snapshot["snapshot"]["readiness_checks"]["critical_failures"] == []
    assert snapshot["snapshot"]["readiness_checks"]["warnings"] == [
        {
            "message": "Working tree has local changes.",
            "remediation": "Review local changes before running scheduling.",
            "details": {
                "code": "working-tree-dirty",
            },
        }
    ]


def test_provider_returns_snapshot_with_critical_failure_when_repo_path_is_not_git(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    provider = SchedulingReadinessProvider(build_config(repo_path=repo_path, worktree_root=worktree_root))

    with patch("bersama.scheduling_readiness.shutil.which", return_value="/usr/bin/gh"):
        snapshot = provider.build_snapshot("demo")

    assert snapshot["repo"] == {
        "name": "demo",
        "path": str(repo_path),
        "main_branch": "main",
        "worktree_root": str(worktree_root),
    }
    assert snapshot["snapshot"]["readiness_checks"]["critical_failures"] == [
        {
            "message": "Target repository is not a Git repository.",
            "remediation": "Use a repository checkout with Git metadata available.",
            "details": {
                "code": "non-git-target-repo",
                "path": str(repo_path),
            },
        }
    ]


def test_provider_reports_invalid_config_as_critical_failure_when_harness_is_missing(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    config = build_config(repo_path=repo_path, worktree_root=worktree_root, default_harness="missing")
    provider = SchedulingReadinessProvider(config)

    with (
        patch("bersama.scheduling_readiness.shutil.which", return_value="/usr/bin/gh"),
        patch("bersama.scheduling_readiness.os.access", return_value=True),
        patch("bersama.scheduling_readiness._run_command") as run_command,
    ):
        run_command.side_effect = [
            _completed(stdout="WRITE"),
            _completed(stdout="\n".join(
                [
                    "prd",
                    "implementation",
                    "ready-for-agent",
                    "claimed",
                    "needs-info",
                    "needs-triage",
                    "ready-for-human",
                    "wontfix",
                ]
            )),
            _completed(stdout=""),
            _completed(),
            _completed(stdout='{"name":"demo"}'),
        ]

        snapshot = provider.build_snapshot("demo")

    assert {
        "message": "Default harness configuration is missing.",
        "remediation": "Set a valid default harness for the repository.",
        "details": {
            "code": "missing-default-harness",
        },
    } in snapshot["snapshot"]["readiness_checks"]["critical_failures"]


def test_provider_reports_missing_harness_command_using_path_resolution_only(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    provider = SchedulingReadinessProvider(build_config(repo_path=repo_path, worktree_root=worktree_root))

    with (
        patch("bersama.scheduling_readiness.shutil.which", side_effect=lambda command: None if command == "codex" else "/usr/bin/gh"),
        patch("bersama.scheduling_readiness.os.access", return_value=True),
        patch("bersama.scheduling_readiness._run_command") as run_command,
    ):
        run_command.side_effect = [
            _completed(stdout="WRITE"),
            _completed(stdout="\n".join(
                [
                    "prd",
                    "implementation",
                    "ready-for-agent",
                    "claimed",
                    "needs-info",
                    "needs-triage",
                    "ready-for-human",
                    "wontfix",
                ]
            )),
            _completed(stdout=""),
            _completed(),
            _completed(stdout='{"name":"demo"}'),
        ]

        snapshot = provider.build_snapshot("demo")

    assert snapshot["snapshot"]["readiness_checks"]["critical_failures"] == [
        {
            "message": "Configured harness command is not available.",
            "remediation": "Install the configured harness command or update the harness configuration.",
            "details": {
                "code": "harness-command-missing",
                "harness": "local",
            },
        }
    ]


def _completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
):
    class Completed:
        def __init__(self) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return Completed()
