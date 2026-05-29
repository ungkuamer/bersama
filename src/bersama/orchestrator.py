from __future__ import annotations

from dataclasses import dataclass

from bersama.config import AppConfig


@dataclass(frozen=True)
class RunPlan:
    repo_name: str
    repo_path: str
    main_branch: str
    worktree_root: str
    harness_name: str
    command: tuple[str, ...]


def build_run_plan(config: AppConfig, repo_name: str) -> RunPlan:
    repo = config.repo(repo_name)
    harness = config.harness(repo.default_harness)

    format_context = {
        "repo_name": repo.name,
        "repo_path": str(repo.repo_path),
        "main_branch": repo.main_branch,
        "worktree_root": str(repo.worktree_root),
        "global_concurrency": str(repo.global_concurrency),
        "per_prd_concurrency": str(repo.per_prd_concurrency),
        "harness_name": harness.name,
    }

    rendered_args = tuple(
        part.format(**format_context) for part in harness.args_template
    )
    command = (harness.command, *rendered_args)

    return RunPlan(
        repo_name=repo.name,
        repo_path=str(repo.repo_path),
        main_branch=repo.main_branch,
        worktree_root=str(repo.worktree_root),
        harness_name=harness.name,
        command=command,
    )
