from __future__ import annotations

import argparse
import sys

from bersama.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from bersama.config import ConfigError, load_config
from bersama.github_issues import create_bounded_issue_gateway
from bersama.execution import HarnessExecutionService
from bersama.orchestrator import build_run_plan
from bersama.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from bersama.integration import IntegrationService, IntegrationWorkspaceGateway
from bersama.reconciliation import ReconciliationService


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
    run_parser.add_argument(
        "--continuous",
        action="store_true",
        help="Continuously claim and execute ready issues until no more claimable issues remain.",
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

    claim_parser = subparsers.add_parser(
        "claim-issue",
        help="Claim a ready Implementation Issue and create its isolated worktree.",
    )
    claim_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    claim_parser.add_argument("issue_number", type=int, help="Implementation Issue number.")
    claim_parser.add_argument(
        "--agent-run-id",
        required=True,
        help="Unique agent run identity to record in issue orchestration metadata.",
    )
    claim_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    claim_parser.set_defaults(handler=_claim_issue_command)

    execute_parser = subparsers.add_parser(
        "execute-run",
        help="Execute the agent harness for a claimed Implementation Issue.",
    )
    execute_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    execute_parser.add_argument("issue_number", type=int, help="Implementation Issue number.")
    execute_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    execute_parser.set_defaults(handler=_execute_run_command)

    integrate_parser = subparsers.add_parser(
        "integrate-run",
        help="Integrate a successful Agent Run by merging its implementation branch back into its parent PRD branch.",
    )
    integrate_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    integrate_parser.add_argument("issue_number", type=int, help="Implementation Issue number.")
    integrate_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    integrate_parser.set_defaults(handler=_integrate_run_command)

    reconcile_parser = subparsers.add_parser(
        "reconcile",
        help="Reconcile issue lifecycle states and mark parent PRD Issues ready-for-human.",
    )
    reconcile_parser.add_argument("repo_name", help="Named repo from the YAML config.")
    reconcile_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    reconcile_parser.set_defaults(handler=_reconcile_command)

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Start the read-only FastAPI dashboard backend.",
    )
    dashboard_parser.add_argument(
        "--config",
        default="bersama.yaml",
        help="Path to the YAML config file. Defaults to ./bersama.yaml",
    )
    dashboard_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to. Defaults to 127.0.0.1",
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to. Defaults to 8000",
    )
    dashboard_parser.set_defaults(handler=_dashboard_command)

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

    repo = config.repo(args.repo_name)
    issues_gateway = create_bounded_issue_gateway(cwd=repo.repo_path)

    from bersama.orchestrator import Orchestrator
    orchestrator = Orchestrator(issues_gateway=issues_gateway)
    orchestrator.run(args.repo_name, config, continuous=args.continuous)
    return 0


def _reconcile_safe(repo_name: str, config: AppConfig) -> None:
    try:
        repo = config.repo(repo_name)
        service = ReconciliationService(issues=create_bounded_issue_gateway(cwd=repo.repo_path))
        service.reconcile()
    except Exception as exc:
        print(f"Warning: Issue state reconciliation failed: {exc}", file=sys.stderr)


def _prepare_prd_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)

    service = PrdPreparationService(
        issues=create_bounded_issue_gateway(cwd=repo.repo_path),
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
    _reconcile_safe(args.repo_name, config)
    return 0


def _claim_issue_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)

    service = ImplementationClaimService(
        issues=create_bounded_issue_gateway(cwd=repo.repo_path),
        workspace=ClaimWorkspaceGateway(),
    )
    result = service.claim_issue(
        repo_path=str(repo.repo_path),
        worktree_root=str(repo.worktree_root),
        issue_number=args.issue_number,
        agent_run_id=args.agent_run_id,
    )

    if not result.succeeded:
        print(
            f"Failed to claim implementation issue #{result.issue_number}: {result.failure_message}",
            file=sys.stderr,
        )
        _reconcile_safe(args.repo_name, config)
        return 1

    print(f"Claimed implementation issue #{result.issue_number}")
    print(f"Agent run: {result.agent_run_id}")
    print(f"Implementation branch: {result.implementation_branch}")
    print(f"Worktree: {result.worktree_path}")
    _reconcile_safe(args.repo_name, config)
    return 0


def _execute_run_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)

    service = HarnessExecutionService(
        issues=create_bounded_issue_gateway(cwd=repo.repo_path),
    )
    try:
        result = service.execute_run(
            repo_name=args.repo_name,
            issue_number=args.issue_number,
            config=config,
        )
    except Exception as exc:
        print(f"Execution setup failed: {exc}", file=sys.stderr)
        _reconcile_safe(args.repo_name, config)
        return 1

    _reconcile_safe(args.repo_name, config)
    if result.status == "succeeded":
        print(f"Harness execution succeeded for issue #{result.issue_number}")
        print(f"Exit code: {result.exit_code}")
        print(f"New commit: Yes")
        print(f"Log path: {result.log_path}")
        print(f"Run state: {result.run_state_path}")
        return 0
    else:
        print(f"Harness execution failed for issue #{result.issue_number}: {result.failure_reason}", file=sys.stderr)
        print(f"Exit code: {result.exit_code}", file=sys.stderr)
        print(f"New commit: {'Yes' if result.new_commits else 'No'}", file=sys.stderr)
        return 1


def _integrate_run_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)

    service = IntegrationService(
        issues=create_bounded_issue_gateway(cwd=repo.repo_path),
        workspace=IntegrationWorkspaceGateway(),
    )
    result = service.integrate_issue(
        repo_path=str(repo.repo_path),
        worktree_root=str(repo.worktree_root),
        issue_number=args.issue_number,
    )

    _reconcile_safe(args.repo_name, config)
    if result.succeeded:
        print(f"Successfully integrated issue #{result.issue_number}")
        print(f"Implementation branch: {result.implementation_branch}")
        print(f"PRD branch: {result.prd_branch}")
        return 0
    else:
        print(f"Failed to integrate issue #{result.issue_number}: {result.failure_message}", file=sys.stderr)
        print(f"Failure type: {result.failure_type}", file=sys.stderr)
        return 1


def _reconcile_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = config.repo(args.repo_name)
    service = ReconciliationService(issues=create_bounded_issue_gateway(cwd=repo.repo_path))
    service.reconcile()
    print(f"Successfully reconciled issue states for repo: {args.repo_name}")
    return 0


def _dashboard_command(args: argparse.Namespace) -> int:
    import uvicorn
    from bersama.dashboard import create_dashboard_app

    config = load_config(args.config)
    app = create_dashboard_app(config=config)

    print(f"Starting dashboard backend on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
