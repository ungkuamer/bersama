from __future__ import annotations

import argparse
import sys

from bersama.config import ConfigError, load_config
from bersama.github_issues import GitHubIssueGateway
from bersama.orchestrator import build_run_plan
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bersama")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Load config for one repo and print the selected orchestration plan.",
    )
    run_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    run_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    run_parser.set_defaults(handler=_run_command)

    prepare_prd_parser = subparsers.add_parser(
        "prepare-prd",
        help="Create or reuse a PRD branch for a PRD Issue and record it in the issue body.",
    )
    prepare_prd_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    prepare_prd_parser.add_argument("issue_number", type=int, help="PRD Issue number.")
    prepare_prd_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    prepare_prd_parser.set_defaults(handler=_prepare_prd_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


def _run_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    plan = build_run_plan(config, args.repo_name)

    print(f"Selected repo: {plan.repo_name}")
    print(f"Repo path: {plan.repo_path}")
    print(f"Main branch: {plan.main_branch}")
    print(f"Worktree root: {plan.worktree_root}")
    print(f"Harness: {plan.harness_name}")
    print("Command: " + " ".join(plan.command))
    return 0


def _prepare_prd_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)

    service = PrdPreparationService(
        issues=GitHubIssueGateway(),
        workspace=GitWorkspaceGateway(),
    )
    result = service.prepare_issue(
        repo_path=str(repo.repo_path),
        main_branch=repo.main_branch,
        issue_number=args.issue_number,
    )

    if not result.succeeded:
        print(
            f"Failed to prepare PRD issue #{result.issue_number}: {result.failure_message}",
            file=sys.stderr,
        )
        return 1

    branch_state = "reused" if result.reused_existing_branch else "created"
    print(f"Prepared PRD issue #{result.issue_number}")
    print(f"PRD branch: {result.prd_branch} ({branch_state})")
    print(f"Issue body updated: {'yes' if result.updated_issue_body else 'no'}")
    return 0
