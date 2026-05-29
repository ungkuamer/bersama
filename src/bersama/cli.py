from __future__ import annotations

import argparse
import sys

from bersama.config import ConfigError, load_config
from bersama.orchestrator import build_run_plan


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
