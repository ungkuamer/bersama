from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import subprocess

from bersama.config import AppConfig, ConfigError, RepoConfig


REQUIRED_LABELS = (
    "prd",
    "implementation",
    "ready-for-agent",
    "claimed",
    "needs-info",
    "needs-triage",
    "ready-for-human",
    "wontfix",
)


@dataclass(frozen=True)
class ReadinessCheck:
    message: str
    remediation: str
    details: dict[str, object]


@dataclass(frozen=True)
class CheckProviderContext:
    repo_name: str
    repo: RepoConfig | None
    config: AppConfig
    harness_name: str | None
    harness_configured: bool
    harness_command: str | None


class ReadinessCheckProvider:
    def evaluate(self, context: CheckProviderContext) -> tuple[list[ReadinessCheck], list[ReadinessCheck]]:
        raise NotImplementedError


@dataclass(frozen=True)
class SchedulingReadinessProvider:
    config: AppConfig
    check_providers: tuple[ReadinessCheckProvider, ...] = ()

    def __post_init__(self) -> None:
        if not self.check_providers:
            object.__setattr__(
                self,
                "check_providers",
                (
                    ConfigReadinessCheckProvider(),
                    RepositoryReadinessCheckProvider(),
                    GitHubReadinessCheckProvider(),
                    HarnessReadinessCheckProvider(),
                ),
            )

    def build_snapshot(self, repo_name: str) -> dict[str, object]:
        observed_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        repo, repo_error = _safe_repo_lookup(self.config, repo_name)
        harness_name = repo.default_harness if repo is not None else None
        harness_configured = _has_harness(self.config, harness_name)
        harness_command = _safe_harness_command(self.config, harness_name)
        checks = self._evaluate_checks(
            CheckProviderContext(
                repo_name=repo_name,
                repo=repo,
                config=self.config,
                harness_name=harness_name,
                harness_configured=harness_configured,
                harness_command=harness_command,
            )
        )

        if repo_error is not None:
            checks["critical_failures"].insert(
                0,
                ReadinessCheck(
                    message="Scheduling configuration is invalid.",
                    remediation="Review the repository configuration and correct the missing or invalid setting.",
                    details={
                        "code": "invalid-config",
                        "error": str(repo_error),
                    },
                ),
            )

        return {
            "repo": _serialize_repo(repo_name, repo),
            "snapshot": {
                "observed_at": observed_at,
                "config_provenance": {
                    "source": "app-config",
                    "default_harness": {
                        "name": harness_name,
                        "timeout_seconds": _safe_harness_timeout(self.config, harness_name),
                    },
                },
                "harness_summary": {
                    "default_harness": harness_name,
                    "timeout_seconds": _safe_harness_timeout(self.config, harness_name),
                },
                "readiness_checks": {
                    "critical_failures": [check.__dict__ for check in checks["critical_failures"]],
                    "warnings": [check.__dict__ for check in checks["warnings"]],
                },
                "implementation_issue_state": _build_empty_implementation_issue_state(),
            },
        }

    def _evaluate_checks(self, context: CheckProviderContext) -> dict[str, list[ReadinessCheck]]:
        critical_failures: list[ReadinessCheck] = []
        warnings: list[ReadinessCheck] = []
        for provider in self.check_providers:
            provider_critical, provider_warnings = provider.evaluate(context)
            critical_failures.extend(provider_critical)
            warnings.extend(provider_warnings)
        return {
            "critical_failures": critical_failures,
            "warnings": warnings,
        }


class ConfigReadinessCheckProvider(ReadinessCheckProvider):
    def evaluate(self, context: CheckProviderContext) -> tuple[list[ReadinessCheck], list[ReadinessCheck]]:
        if context.repo is not None:
            return ([], [])
        return (
            [
                ReadinessCheck(
                    message="Scheduling configuration is invalid.",
                    remediation="Review the repository configuration and correct the missing or invalid setting.",
                    details={
                        "code": "invalid-config",
                    },
                )
            ],
            [],
        )


class RepositoryReadinessCheckProvider(ReadinessCheckProvider):
    def evaluate(self, context: CheckProviderContext) -> tuple[list[ReadinessCheck], list[ReadinessCheck]]:
        if context.repo is None:
            return ([], [])

        critical_failures: list[ReadinessCheck] = []
        warnings: list[ReadinessCheck] = []

        repo_path = context.repo.repo_path
        if not repo_path.exists():
            critical_failures.append(
                ReadinessCheck(
                    message="Target repository path does not exist.",
                    remediation="Point the repo configuration at an existing local checkout.",
                    details={
                        "code": "missing-target-repo",
                        "path": str(repo_path),
                    },
                )
            )
            return (critical_failures, warnings)

        if not (repo_path / ".git").exists():
            critical_failures.append(
                ReadinessCheck(
                    message="Target repository is not a Git repository.",
                    remediation="Use a repository checkout with Git metadata available.",
                    details={
                        "code": "non-git-target-repo",
                        "path": str(repo_path),
                    },
                )
            )
            return (critical_failures, warnings)

        worktree_root = context.repo.worktree_root
        if not os.access(worktree_root, os.W_OK):
            critical_failures.append(
                ReadinessCheck(
                    message="Worktree root is not writable.",
                    remediation="Choose a writable worktree root before running scheduling.",
                    details={
                        "code": "worktree-root-not-writable",
                        "path": str(worktree_root),
                    },
                )
            )

        permission = _git_permission(context.repo.repo_path)
        if permission is None:
            critical_failures.append(
                ReadinessCheck(
                    message="Repository permissions could not be determined.",
                    remediation="Verify repository access and GitHub visibility before running scheduling.",
                    details={
                        "code": "repo-permission-unknown",
                    },
                )
            )
        elif not permission.get("push", False):
            critical_failures.append(
                ReadinessCheck(
                    message="Repository does not allow push access.",
                    remediation="Use a repository where the scheduler can write branches when needed.",
                    details={
                        "code": "repo-push-forbidden",
                        "permissions": permission,
                    },
                )
            )

        labels = _fetch_repo_labels(context.repo.repo_path)
        if labels is None:
            critical_failures.append(
                ReadinessCheck(
                    message="Repository labels could not be read from GitHub.",
                    remediation="Verify GitHub access for the target repository.",
                    details={
                        "code": "labels-unreadable",
                    },
                )
            )
        else:
            missing = sorted(label for label in REQUIRED_LABELS if label not in labels)
            if missing:
                critical_failures.append(
                    ReadinessCheck(
                        message="Required repository labels are missing.",
                        remediation="Add the required labels in GitHub before running scheduling.",
                        details={
                            "code": "missing-required-labels",
                            "missing_labels": missing,
                        },
                    )
                )

        if _working_tree_dirty(context.repo.repo_path):
            warnings.append(
                ReadinessCheck(
                    message="Working tree has local changes.",
                    remediation="Review local changes before running scheduling.",
                    details={
                        "code": "working-tree-dirty",
                    },
                )
            )

        return (critical_failures, warnings)


class GitHubReadinessCheckProvider(ReadinessCheckProvider):
    def evaluate(self, context: CheckProviderContext) -> tuple[list[ReadinessCheck], list[ReadinessCheck]]:
        if context.repo is None:
            return ([], [])
        if not context.repo.repo_path.exists() or not (context.repo.repo_path / ".git").exists():
            return ([], [])

        critical_failures: list[ReadinessCheck] = []

        if shutil.which("gh") is None:
            critical_failures.append(
                ReadinessCheck(
                    message="GitHub CLI is not available.",
                    remediation="Install GitHub CLI where the scheduler runs.",
                    details={
                        "code": "gh-cli-missing",
                    },
                )
            )
            return (critical_failures, [])

        auth_status = _run_command(("gh", "auth", "status"), cwd=context.repo.repo_path)
        if auth_status.returncode != 0:
            critical_failures.append(
                ReadinessCheck(
                    message="GitHub CLI is not authenticated.",
                    remediation="Sign in to GitHub CLI for the scheduler environment.",
                    details={
                        "code": "gh-auth-missing",
                        "stderr": auth_status.stderr.strip(),
                    },
                )
            )
            return (critical_failures, [])

        repo_view = _run_command(("gh", "repo", "view", "--json", "name"), cwd=context.repo.repo_path)
        if repo_view.returncode != 0:
            critical_failures.append(
                ReadinessCheck(
                    message="Target repository could not be read from GitHub.",
                    remediation="Verify repository visibility and API access before running scheduling.",
                    details={
                        "code": "github-repo-unreadable",
                        "stderr": repo_view.stderr.strip(),
                    },
                )
            )

        return (critical_failures, [])


class HarnessReadinessCheckProvider(ReadinessCheckProvider):
    def evaluate(self, context: CheckProviderContext) -> tuple[list[ReadinessCheck], list[ReadinessCheck]]:
        if context.harness_name is None:
            return (
                [
                    ReadinessCheck(
                        message="Default harness configuration is missing.",
                        remediation="Set a valid default harness for the repository.",
                        details={
                            "code": "missing-default-harness",
                        },
                    )
                ],
                [],
            )

        if not context.harness_configured:
            return (
                [
                    ReadinessCheck(
                        message="Default harness configuration is missing.",
                        remediation="Set a valid default harness for the repository.",
                        details={
                            "code": "missing-default-harness",
                        },
                    )
                ],
                [],
            )

        if context.harness_command is None:
            return (
                [
                    ReadinessCheck(
                        message="Configured harness command is not available.",
                        remediation="Install the configured harness command or update the harness configuration.",
                        details={
                            "code": "harness-command-missing",
                            "harness": context.harness_name,
                        },
                    )
                ],
                [],
            )

        if shutil.which(context.harness_command) is None:
            return (
                [
                    ReadinessCheck(
                        message="Configured harness command is not available.",
                        remediation="Install the configured harness command or update the harness configuration.",
                        details={
                            "code": "harness-command-missing",
                            "harness": context.harness_name,
                        },
                    )
                ],
                [],
            )

        return ([], [])


def _serialize_repo(repo_name: str, repo: RepoConfig | None) -> dict[str, str | None]:
    if repo is None:
        return {
            "name": repo_name,
            "path": None,
            "main_branch": None,
            "worktree_root": None,
        }
    return {
        "name": repo.name,
        "path": str(repo.repo_path),
        "main_branch": repo.main_branch,
        "worktree_root": str(repo.worktree_root),
    }


def _build_empty_implementation_issue_state() -> dict[str, object]:
    return {
        "items": [],
        "summary": {
            "ready": 0,
            "blocked": 0,
            "claimed": 0,
            "running": 0,
            "failed": 0,
            "succeeded": 0,
            "other": 0,
        },
    }


def _safe_repo_lookup(config: AppConfig, repo_name: str) -> tuple[RepoConfig | None, ConfigError | None]:
    try:
        return (config.repo(repo_name), None)
    except ConfigError as exc:
        return (None, exc)


def _safe_harness_timeout(config: AppConfig, harness_name: str | None) -> int | None:
    if harness_name is None:
        return None
    try:
        return config.harness(harness_name).timeout_seconds
    except ConfigError:
        return None


def _safe_harness_command(config: AppConfig, harness_name: str | None) -> str | None:
    if harness_name is None:
        return None
    try:
        return config.harness(harness_name).command
    except ConfigError:
        return None


def _has_harness(config: AppConfig, harness_name: str | None) -> bool:
    if harness_name is None:
        return False
    try:
        config.harness(harness_name)
    except ConfigError:
        return False
    return True


def _run_command(command: tuple[str, ...], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _fetch_repo_labels(repo_path: Path) -> set[str] | None:
    result = _run_command(
        ("gh", "label", "list", "--json", "name", "--jq", ".[].name"),
        cwd=repo_path,
    )
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _git_permission(repo_path: Path) -> dict[str, object] | None:
    result = _run_command(
        ("gh", "repo", "view", "--json", "viewerPermission"),
        cwd=repo_path,
    )
    if result.returncode != 0:
        return None
    permission = result.stdout.strip()
    if not permission:
        return None
    return {
        "viewer_permission": permission,
        "push": permission in {"ADMIN", "MAINTAIN", "WRITE"},
    }


def _working_tree_dirty(repo_path: Path) -> bool:
    result = _run_command(("git", "status", "--porcelain"), cwd=repo_path)
    return result.returncode == 0 and bool(result.stdout.strip())
