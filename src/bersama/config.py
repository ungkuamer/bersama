from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


@dataclass(frozen=True)
class HarnessConfig:
    name: str
    command: str
    args_template: tuple[str, ...]


@dataclass(frozen=True)
class RepoConfig:
    name: str
    repo_path: Path
    main_branch: str
    worktree_root: Path
    global_concurrency: int
    per_prd_concurrency: int
    default_harness: str


@dataclass(frozen=True)
class AppConfig:
    repos: dict[str, RepoConfig]
    harnesses: dict[str, HarnessConfig]

    def repo(self, name: str) -> RepoConfig:
        try:
            return self.repos[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.repos))
            raise ConfigError(
                f"Unknown repo '{name}'. Available repos: {available or '(none)'}."
            ) from exc

    def harness(self, name: str) -> HarnessConfig:
        try:
            return self.harnesses[name]
        except KeyError as exc:
            raise ConfigError(f"Unknown harness '{name}'.") from exc


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc

    try:
        data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping.")

    harnesses = _parse_harnesses(data.get("harnesses"))
    repos = _parse_repos(data.get("repos"), harnesses)
    return AppConfig(repos=repos, harnesses=harnesses)


def _parse_harnesses(raw_harnesses: object) -> dict[str, HarnessConfig]:
    if not isinstance(raw_harnesses, dict) or not raw_harnesses:
        raise ConfigError("Config must define at least one harness in 'harnesses'.")

    harnesses: dict[str, HarnessConfig] = {}
    for name, raw_value in raw_harnesses.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("Harness names must be non-empty strings.")
        if not isinstance(raw_value, dict):
            raise ConfigError(f"Harness '{name}' must be a mapping.")

        command = _require_string(raw_value, "command", context=f"harness '{name}'")
        args_template = _parse_string_list(
            raw_value.get("args_template", []),
            context=f"harness '{name}' args_template",
        )
        harnesses[name] = HarnessConfig(
            name=name,
            command=command,
            args_template=tuple(args_template),
        )

    return harnesses


def _parse_repos(
    raw_repos: object, harnesses: dict[str, HarnessConfig]
) -> dict[str, RepoConfig]:
    if not isinstance(raw_repos, dict) or not raw_repos:
        raise ConfigError("Config must define at least one repo in 'repos'.")

    repos: dict[str, RepoConfig] = {}
    for name, raw_value in raw_repos.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("Repo names must be non-empty strings.")
        if not isinstance(raw_value, dict):
            raise ConfigError(f"Repo '{name}' must be a mapping.")

        global_concurrency = _parse_positive_int(
            raw_value.get("global_concurrency", 1),
            context=f"repo '{name}' global_concurrency",
        )
        per_prd_concurrency = _parse_positive_int(
            raw_value.get("per_prd_concurrency", global_concurrency),
            context=f"repo '{name}' per_prd_concurrency",
        )

        default_harness = _require_string(
            raw_value, "default_harness", context=f"repo '{name}'"
        )
        if default_harness not in harnesses:
            raise ConfigError(
                f"Repo '{name}' references unknown harness '{default_harness}'."
            )

        repos[name] = RepoConfig(
            name=name,
            repo_path=Path(
                _require_string(raw_value, "repo_path", context=f"repo '{name}'")
            ),
            main_branch=_require_string(
                raw_value, "main_branch", context=f"repo '{name}'"
            ),
            worktree_root=Path(
                _require_string(raw_value, "worktree_root", context=f"repo '{name}'")
            ),
            global_concurrency=global_concurrency,
            per_prd_concurrency=per_prd_concurrency,
            default_harness=default_harness,
        )

    return repos


def _require_string(data: dict[str, object], key: str, *, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must define non-empty '{key}'.")
    return value


def _parse_string_list(value: object, *, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ConfigError(f"{context} must be a list of strings.")
    if any(not isinstance(item, str) for item in value):
        raise ConfigError(f"{context} must be a list of strings.")
    return value


def _parse_positive_int(value: object, *, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{context} must be a positive integer.")
    return value
