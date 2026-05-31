from __future__ import annotations

import json
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
            _completed(stdout="[]"),
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
            _completed(stdout="[]"),
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
            _completed(stdout="[]"),
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
            _completed(stdout="[]"),
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


def test_provider_builds_prd_grouped_implementation_issue_state_capacity_and_warnings(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    provider = SchedulingReadinessProvider(build_config(repo_path=repo_path, worktree_root=worktree_root))

    running_worktree = worktree_root / "issue-14"
    running_worktree.mkdir()
    (running_worktree / "run-state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "started_at": "2026-05-31T18:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    failed_worktree = worktree_root / "issue-15"
    failed_worktree.mkdir()
    (failed_worktree / "run-state.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "started_at": "2026-05-31T17:30:00Z",
                "finished_at": "2026-05-31T17:40:00Z",
                "failure_reason": "Tests failed",
            }
        ),
        encoding="utf-8",
    )

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
            _completed(stdout=json.dumps(
                [
                    {
                        "number": 10,
                        "title": "Prepared PRD",
                        "body": "## Problem Statement\n\nPlan work.\n\n## Orchestration\n- PRD Branch: prd/10-prepared",
                        "labels": [{"name": "prd"}],
                        "state": "open",
                    },
                    {
                        "number": 11,
                        "title": "Unprepared PRD",
                        "body": "## Problem Statement\n\nNeeds preparation.",
                        "labels": [{"name": "prd"}],
                        "state": "open",
                    },
                    {
                        "number": 12,
                        "title": "Ready issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nShip it.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "ready-for-agent"}],
                        "state": "open",
                    },
                    {
                        "number": 13,
                        "title": "Blocked issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nWait for ready issue.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\n#12"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "ready-for-agent"}],
                        "state": "open",
                    },
                    {
                        "number": 14,
                        "title": "Running issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nExecute it.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone\n\n"
                            "## Orchestration\n"
                            "- Agent Run: run-14\n"
                            "- Claimed At: 2026-05-31T18:05:00Z\n"
                            "- Claim Status: active\n"
                            "- Implementation Branch: impl/10/14-running\n"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "claimed"}],
                        "state": "open",
                    },
                    {
                        "number": 15,
                        "title": "Failed issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nFail it.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone\n\n"
                            "## Orchestration\n"
                            "- Agent Run: run-15\n"
                            "- Claimed At: 2026-05-31T17:20:00Z\n"
                            "- Claim Status: active\n"
                            "- Implementation Branch: impl/10/15-failed\n"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "claimed"}],
                        "state": "open",
                    },
                    {
                        "number": 16,
                        "title": "Stale claim",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nThis claim is stale.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone\n\n"
                            "## Orchestration\n"
                            "- Agent Run: run-16\n"
                            "- Claimed At: 2026-05-31T12:00:00Z\n"
                            "- Claim Status: active\n"
                            "- Implementation Branch: impl/10/16-stale\n"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "claimed"}],
                        "state": "open",
                    },
                    {
                        "number": 17,
                        "title": "Needs info issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nNeed more details.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone"
                        ),
                        "labels": [{"name": "implementation"}, {"name": "needs-info"}],
                        "state": "open",
                    },
                    {
                        "number": 18,
                        "title": "Closed integrated issue",
                        "body": (
                            "## Parent PRD\n#10\n\n"
                            "## What to Build\nAlready done.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone\n\n"
                            "## Orchestration\n"
                            "- Agent Run: run-18\n"
                            "- Claimed At: 2026-05-31T10:00:00Z\n"
                            "- Implementation Branch: impl/10/18-done\n"
                            "- Integration PR: #123\n"
                            "- Integration Status: merged\n"
                        ),
                        "labels": [{"name": "implementation"}],
                        "state": "closed",
                    },
                    {
                        "number": 19,
                        "title": "Issue under unprepared PRD",
                        "body": (
                            "## Parent PRD\n#11\n\n"
                            "## What to Build\nBlocked by unprepared PRD.\n\n"
                            "## Acceptance Criteria\n- [ ] Done.\n\n"
                            "## Blocked By\nNone"
                        ),
                        "labels": [{"name": "implementation"}],
                        "state": "open",
                    },
                ]
            )),
        ]

        snapshot = provider.build_snapshot("demo")

    implementation_issue_state = snapshot["snapshot"]["implementation_issue_state"]
    assert implementation_issue_state["agent_run_capacity"] == {
        "used": 1,
        "total": 1,
    }
    assert implementation_issue_state["summary"] == {
        "ready": 1,
        "blocked": 1,
        "claimed": 1,
        "running": 1,
        "failed": 1,
        "succeeded": 0,
        "other": 2,
    }
    assert [group["parent_prd"]["issue_number"] for group in implementation_issue_state["groups"]] == [10, 11]
    assert [item["issue_number"] for item in implementation_issue_state["items"]] == [12, 13, 14, 15, 16, 17, 19]
    assert {item["issue_number"]: item["status"] for item in implementation_issue_state["items"]} == {
        12: "ready",
        13: "blocked",
        14: "running",
        15: "failed",
        16: "claimed",
        17: "unready",
        19: "unready",
    }
    assert all(item["issue_number"] != 18 for item in implementation_issue_state["items"])

    warnings = snapshot["snapshot"]["readiness_checks"]["warnings"]
    assert sorted(warning["details"]["code"] for warning in warnings) == sorted([
        "unprepared-prd-issue",
        "blocked-implementation-issue",
        "failed-implementation-issue",
        "stale-claim",
        "needs-info-implementation-issue",
    ])
    assert implementation_issue_state["groups"][0]["items"] == [
        {
            "issue_number": 12,
            "title": "Ready issue",
            "status": "ready",
            "blocked_by": [],
            "active_blockers": [],
        },
        {
            "issue_number": 13,
            "title": "Blocked issue",
            "status": "blocked",
            "blocked_by": [12],
            "active_blockers": [12],
        },
        {
            "issue_number": 14,
            "title": "Running issue",
            "status": "running",
            "blocked_by": [],
            "active_blockers": [],
        },
        {
            "issue_number": 15,
            "title": "Failed issue",
            "status": "failed",
            "blocked_by": [],
            "active_blockers": [],
        },
        {
            "issue_number": 16,
            "title": "Stale claim",
            "status": "claimed",
            "blocked_by": [],
            "active_blockers": [],
        },
        {
            "issue_number": 17,
            "title": "Needs info issue",
            "status": "unready",
            "blocked_by": [],
            "active_blockers": [],
        },
    ]
    assert all("x" not in item and "y" not in item for item in implementation_issue_state["items"])


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
