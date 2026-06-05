from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
import json

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

from rangkai.claiming import ClaimWorkspaceGateway, ImplementationClaimService
from rangkai.config import AppConfig, ConfigError, RepoConfig
from rangkai.execution import HarnessExecutionService
from rangkai.event_bus import EventBus
from rangkai.file_watcher import FileWatcherService
from rangkai.github_issues import GitHubIssueGateway, create_bounded_issue_gateway
from rangkai.integration import IntegrationService, IntegrationWorkspaceGateway
from rangkai.issues import GitHubIssue, ImplementationIssue, parse_issue
from rangkai.prd_preparation import GitWorkspaceGateway, PrdPreparationService
from rangkai.reconciliation import ReconciliationService
from rangkai.repo_lock import RepoLock
from rangkai.scheduling_readiness import SchedulingReadinessProvider
from rangkai.command_executor import CommandExecutor
from rangkai.telemetry import (
    ImplementationIssueMetricsSnapshot,
    TelemetryAdapter,
    serialize_agent_run_metrics_snapshot,
    serialize_implementation_issue_metrics_snapshot,
    serialize_prd_metrics_snapshot,
)

ReconciliationServiceFactory = Callable[[RepoConfig], ReconciliationService]
PrdPreparationServiceFactory = Callable[[RepoConfig], PrdPreparationService]
ImplementationClaimServiceFactory = Callable[[RepoConfig], ImplementationClaimService]
ExecutionServiceFactory = Callable[[RepoConfig], HarnessExecutionService]
IntegrationServiceFactory = Callable[[RepoConfig], IntegrationService]
IssueGatewayFactory = Callable[[], GitHubIssueGateway]
BackgroundTaskScheduler = Callable[..., object]
FileWatcherFactory = Callable[[EventBus, list[Path]], FileWatcherService]


def _serialize_diagnostics(parsed_issue: object) -> list[dict[str, str]]:
    diagnostics = getattr(parsed_issue, "diagnostics", ())
    return [
        {
            "code": diagnostic.code,
            "kind": diagnostic.kind.value,
            "message": diagnostic.message,
        }
        for diagnostic in diagnostics
    ]


def _issue_number_from_worktree(worktree_path: Path) -> int | None:
    prefix = "issue-"
    if not worktree_path.name.startswith(prefix):
        return None
    suffix = worktree_path.name[len(prefix) :]
    try:
        return int(suffix)
    except ValueError:
        return None


class ClaimImplementationIssueRequest(BaseModel):
    agent_run_id: str


def create_dashboard_app(
    *,
    config: AppConfig,
    reconciliation_service_factory: ReconciliationServiceFactory | None = None,
    prd_preparation_service_factory: PrdPreparationServiceFactory | None = None,
    implementation_claim_service_factory: ImplementationClaimServiceFactory | None = None,
    execution_service_factory: ExecutionServiceFactory | None = None,
    integration_service_factory: IntegrationServiceFactory | None = None,
    issue_gateway_factory: IssueGatewayFactory | None = None,
    background_task_scheduler: BackgroundTaskScheduler | None = None,
    scheduling_readiness_provider: object | None = None,
    file_watcher_factory: FileWatcherFactory | None = None,
) -> FastAPI:
    event_bus = EventBus()
    watcher_factory = file_watcher_factory or (
        lambda event_bus, worktree_roots: FileWatcherService(
            event_bus=event_bus,
            worktree_roots=worktree_roots,
        )
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.event_bus = event_bus
        app.state.file_watcher = watcher_factory(
            app.state.event_bus,
            {repo_name: repo.worktree_root for repo_name, repo in config.repos.items()},
        )
        app.state.file_watcher.start()
        try:
            yield
        finally:
            app.state.file_watcher.stop()

    app = FastAPI(lifespan=lifespan)
    app.state.event_bus = event_bus

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def build_service(repo: RepoConfig) -> ReconciliationService:
        return ReconciliationService(issues=create_bounded_issue_gateway(cwd=repo.repo_path))

    def build_repo_lock(repo: RepoConfig) -> RepoLock:
        return RepoLock(repo_path=str(repo.repo_path))

    def build_command_executor() -> CommandExecutor:
        return CommandExecutor()

    def build_prd_preparation_service(repo: RepoConfig) -> PrdPreparationService:
        return PrdPreparationService(
            issues=create_bounded_issue_gateway(cwd=repo.repo_path),
            workspace=GitWorkspaceGateway(
                lock=build_repo_lock(repo),
                command_executor=build_command_executor(),
            ),
        )

    def build_implementation_claim_service(repo: RepoConfig) -> ImplementationClaimService:
        return ImplementationClaimService(
            issues=create_bounded_issue_gateway(cwd=repo.repo_path),
            workspace=ClaimWorkspaceGateway(
                lock=build_repo_lock(repo),
                command_executor=build_command_executor(),
            ),
        )

    def build_execution_service(repo: RepoConfig) -> HarnessExecutionService:
        return HarnessExecutionService(issues=create_bounded_issue_gateway(cwd=repo.repo_path))

    def build_integration_service(repo: RepoConfig) -> IntegrationService:
        return IntegrationService(
            issues=create_bounded_issue_gateway(cwd=repo.repo_path),
            workspace=IntegrationWorkspaceGateway(
                lock=build_repo_lock(repo),
                command_executor=build_command_executor(),
            ),
        )

    service_factory = reconciliation_service_factory or build_service
    prd_service_factory = (
        prd_preparation_service_factory or build_prd_preparation_service
    )
    claim_service_factory = (
        implementation_claim_service_factory or build_implementation_claim_service
    )
    execute_service_factory = execution_service_factory or build_execution_service
    integrate_service_factory = integration_service_factory or build_integration_service
    issues_factory = issue_gateway_factory or (lambda: create_bounded_issue_gateway())
    readiness_provider = scheduling_readiness_provider or SchedulingReadinessProvider(config)

    def schedule_background_task(
        background_tasks: BackgroundTasks,
        task: Callable[..., object],
        *args: object,
    ) -> None:
        if background_task_scheduler is not None:
            background_task_scheduler(task, *args)
            return
        background_tasks.add_task(task, *args)

    def run_issue_execution_in_background(repo_name: str, issue_number: int) -> None:
        repo = config.repo(repo_name)
        execution_result = execute_service_factory(repo).execute_run(
            repo_name=repo_name,
            issue_number=issue_number,
            config=config,
        )
        if execution_result.status == "succeeded":
            service_factory(repo).reconcile()

    def validate_claimed_issue_start(
        repo: RepoConfig, issue_number: int
    ) -> tuple[str, str, str]:
        issue_record = issues_factory().view_issue(issue_number)
        parsed_issue = parse_issue(
            GitHubIssue(
                number=issue_record.number,
                title=issue_record.title,
                body=issue_record.body,
                labels=issue_record.labels,
            )
        )
        if not isinstance(parsed_issue, ImplementationIssue):
            raise HTTPException(status_code=400, detail="Issue is not an Implementation Issue.")

        orchestration = parsed_issue.orchestration
        if not orchestration.agent_run_id or not orchestration.implementation_branch:
            raise HTTPException(status_code=400, detail="Implementation Issue is not claimed.")

        worktree_path = Path(repo.worktree_root) / f"issue-{issue_number}"
        if not worktree_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Implementation Issue worktree does not exist: {worktree_path}",
            )

        return (
            orchestration.agent_run_id,
            str(worktree_path / "run-state.json"),
            str(worktree_path / "harness.log"),
        )

    @app.post("/dashboard/repos/{repo_name}/reconcile")
    def reconcile_repo(repo_name: str) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            service_factory(repo).reconcile()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Reconciliation failed for repo '{repo.name}': {exc}",
            ) from exc

        return {
            "ok": True,
            "repo": repo.name,
            "action": "reconcile",
        }

    @app.post("/dashboard/repos/{repo_name}/prd-issues/{issue_number}/prepare")
    def prepare_prd_issue(repo_name: str, issue_number: int) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = prd_service_factory(repo).prepare_issue(
                repo_path=str(repo.repo_path),
                main_branch=repo.main_branch,
                issue_number=issue_number,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"PRD preparation failed for repo '{repo.name}': {exc}",
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "prepare-prd",
            "status": "prepared",
            "issue_number": result.issue_number,
            "prd_branch": result.prd_branch,
            "reused_existing_branch": result.reused_existing_branch,
            "updated_issue_body": result.updated_issue_body,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/claim")
    def claim_implementation_issue(
        repo_name: str,
        issue_number: int,
        request: ClaimImplementationIssueRequest,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = claim_service_factory(repo).claim_issue(
                repo_path=str(repo.repo_path),
                worktree_root=str(repo.worktree_root),
                issue_number=issue_number,
                agent_run_id=request.agent_run_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Implementation issue claim failed for repo '{repo.name}': {exc}",
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "claim-implementation-issue",
            "status": "claimed",
            "issue_number": result.issue_number,
            "agent_run_id": result.agent_run_id,
            "implementation_branch": result.implementation_branch,
            "worktree_path": result.worktree_path,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/start", status_code=202)
    def start_implementation_issue(
        repo_name: str,
        issue_number: int,
        background_tasks: BackgroundTasks,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            agent_run_id, run_state_path, log_path = validate_claimed_issue_start(
                repo, issue_number
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Implementation issue start failed for repo '{repo.name}': {exc}"
                ),
            ) from exc

        schedule_background_task(
            background_tasks,
            run_issue_execution_in_background,
            repo.name,
            issue_number,
        )

        return {
            "ok": True,
            "repo": repo.name,
            "action": "start-implementation-issue",
            "issue_number": issue_number,
            "agent_run_id": agent_run_id,
            "status": "started",
            "run_state_path": run_state_path,
            "log_path": log_path,
        }

    @app.post("/dashboard/repos/{repo_name}/implementation-issues/{issue_number}/integrate")
    def integrate_implementation_issue(
        repo_name: str,
        issue_number: int,
    ) -> dict[str, object]:
        try:
            repo = config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            result = integrate_service_factory(repo).integrate_issue(
                repo_path=str(repo.repo_path),
                worktree_root=str(repo.worktree_root),
                issue_number=issue_number,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Implementation issue integration failed for repo '{repo.name}': {exc}"
                ),
            ) from exc

        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)

        return {
            "ok": True,
            "repo": repo.name,
            "action": "integrate-implementation-issue",
            "status": "integrated",
            "issue_number": result.issue_number,
            "implementation_branch": result.implementation_branch,
            "prd_branch": result.prd_branch,
        }

    @app.get("/api/repos")
    def get_repos() -> list[dict[str, object]]:
        return [
            {
                "name": repo.name,
                "repo_path": str(repo.repo_path),
                "main_branch": repo.main_branch,
                "worktree_root": str(repo.worktree_root),
                "global_concurrency": repo.global_concurrency,
                "per_prd_concurrency": repo.per_prd_concurrency,
                "default_harness": repo.default_harness,
            }
            for repo in config.repos.values()
        ]

    @app.get("/api/issues")
    def get_issues(repo: str) -> list[dict[str, object]]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        gateway = issues_factory()
        if hasattr(gateway, "_cwd"):
            gateway._cwd = repo_cfg.repo_path

        try:
            issue_records = gateway.list_issues(
                state="all", labels=("prd", "implementation")
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to list GitHub issues: {exc}"
            ) from exc

        records_by_number = {record.number: record for record in issue_records}
        parsed_by_number = {}
        for record in issue_records:
            parsed_by_number[record.number] = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )

        issue_dicts = {}
        for record in issue_records:
            parsed = parsed_by_number.get(record.number)
            if parsed is None:
                continue

            res = {
                "number": record.number,
                "title": record.title,
                "labels": list(record.labels),
                "state": record.state,
                "kind": parsed.kind.value,
            }
            diagnostics = _serialize_diagnostics(parsed)
            if diagnostics:
                res["diagnostics"] = diagnostics

            if parsed.kind.value == "prd":
                res["prd_branch"] = parsed.orchestration.prd_branch
                res["children"] = []
            elif parsed.kind.value == "implementation":
                res["parent_prd_number"] = parsed.parent_prd_number
                res["implementation_branch"] = parsed.orchestration.implementation_branch
                res["agent_run_id"] = parsed.orchestration.agent_run_id
                res["claimed_at"] = parsed.orchestration.claimed_at
                res["blocked_by"] = list(parsed.blocked_by)

                active_blockers = []
                for blocker_num in parsed.blocked_by:
                    blocker_record = records_by_number.get(blocker_num)
                    if blocker_record and blocker_record.state == "open":
                        active_blockers.append(blocker_num)
                res["active_blockers"] = active_blockers

                status = "degraded" if diagnostics else "unknown"
                started_at = None
                finished_at = None
                failure_reason = None
                worktree_path = Path(repo_cfg.worktree_root) / f"issue-{record.number}"
                run_state_path = worktree_path / "run-state.json"

                if diagnostics:
                    pass
                elif record.state == "closed":
                    status = "succeeded"
                else:
                    if run_state_path.exists():
                        try:
                            run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                            status = run_state_data.get("status", "unknown")
                            started_at = run_state_data.get("started_at")
                            finished_at = run_state_data.get("finished_at")
                            failure_reason = run_state_data.get("failure_reason")
                        except Exception:
                            pass
                    else:
                        if parsed.orchestration.agent_run_id or parsed.orchestration.claimed_at:
                            status = "claimed"
                        elif "ready-for-agent" in record.labels:
                            if active_blockers:
                                status = "blocked"
                            else:
                                status = "ready"
                        else:
                            status = "unready"

                # Telemetry diagnostics: check if telemetry is available or unavailable
                telemetry_diagnostics = None
                if config.observability.enabled:
                    if run_state_path.exists():
                        try:
                            run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                            telemetry_assoc = run_state_data.get("telemetry_association")
                            if not isinstance(telemetry_assoc, dict):
                                telemetry_diagnostics = [
                                    {
                                        "code": "missing_association",
                                        "severity": "warning",
                                        "message": "No Run Telemetry Association found. The Agent Run did not declare observability identity at startup.",
                                    }
                                ]
                        except Exception:
                            pass
                    elif parsed.orchestration.agent_run_id:
                        # Agent run exists but no run-state.json found
                        telemetry_diagnostics = [
                            {
                                "code": "missing_association",
                                "severity": "warning",
                                "message": "No Run Telemetry Association found. The Agent Run did not declare observability identity at startup.",
                            }
                        ]
                res["telemetry_diagnostics"] = telemetry_diagnostics

                res["status"] = status
                res["started_at"] = started_at
                res["finished_at"] = finished_at
                res["failure_reason"] = failure_reason
            elif diagnostics:
                res["status"] = "degraded"

            issue_dicts[record.number] = res

        flat_results = []
        for number, item in issue_dicts.items():
            if item["kind"] == "implementation" and item.get("parent_prd_number") is not None:
                parent_num = item["parent_prd_number"]
                if parent_num in issue_dicts and issue_dicts[parent_num]["kind"] == "prd":
                    issue_dicts[parent_num]["children"].append(item)
                    continue
            flat_results.append(item)

        return flat_results

    @app.get("/api/events")
    async def get_events(repo: str) -> EventSourceResponse:
        try:
            config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        async def event_stream():
            async with app.state.event_bus.subscribe() as subscriber:
                async for event in subscriber:
                    if event.data.get("repo") not in (None, repo):
                        continue
                    yield {
                        "event": event.type,
                        "data": json.dumps(event.data),
                    }

        return EventSourceResponse(event_stream())

    @app.get("/api/scheduling-readiness/{repo_name}")
    def get_scheduling_readiness_snapshot(repo_name: str) -> dict[str, object]:
        try:
            config.repo(repo_name)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return readiness_provider.build_snapshot(repo_name)

    @app.get("/api/runs")
    def get_runs(repo: str) -> list[dict[str, object]]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        runs_list = []
        worktree_root = Path(repo_cfg.worktree_root)
        if worktree_root.exists() and worktree_root.is_dir():
            for child in worktree_root.iterdir():
                if child.is_dir() and child.name.startswith("issue-"):
                    run_state_path = child / "run-state.json"
                    if run_state_path.exists():
                        try:
                            run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                            runs_list.append(run_state_data)
                        except json.JSONDecodeError:
                            issue_number = _issue_number_from_worktree(child)
                            degraded_run = {
                                "status": "degraded",
                                "run_state_path": str(run_state_path),
                                "diagnostics": [
                                    {
                                        "code": "invalid-run-state-json",
                                        "kind": "invalid-state",
                                        "message": "Run state file is not valid JSON.",
                                    }
                                ],
                            }
                            if issue_number is not None:
                                degraded_run["issue_number"] = issue_number
                            runs_list.append(degraded_run)
                        except OSError:
                            issue_number = _issue_number_from_worktree(child)
                            degraded_run = {
                                "status": "degraded",
                                "run_state_path": str(run_state_path),
                                "diagnostics": [
                                    {
                                        "code": "unreadable-run-state",
                                        "kind": "read-error",
                                        "message": "Run state file could not be read.",
                                    }
                                ],
                            }
                            if issue_number is not None:
                                degraded_run["issue_number"] = issue_number
                            runs_list.append(degraded_run)

        runs_list.sort(key=lambda r: r.get("issue_number", 0))
        return runs_list

    @app.get("/api/metrics/{repo}/runs/{run_issue_number}")
    def get_run_metrics(repo: str, run_issue_number: int) -> dict[str, object]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        adapter = TelemetryAdapter(config=config.observability)

        # Look up the telemetry association from the worktree run-state
        worktree_path = Path(repo_cfg.worktree_root) / f"issue-{run_issue_number}"
        run_state_path = worktree_path / "run-state.json"

        association = None
        if run_state_path.exists():
            try:
                run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                association = run_state_data.get("telemetry_association")
            except Exception:
                pass

        run_id = None
        if isinstance(association, dict):
            run_id = str(association.get("run_id", ""))
        else:
            # Fallback: check the issues endpoint data for agent_run_id
            issue_record = issues_factory().view_issue(run_issue_number)
            parsed_issue = parse_issue(
                GitHubIssue(
                    number=issue_record.number,
                    title=issue_record.title,
                    body=issue_record.body,
                    labels=issue_record.labels,
                )
            )
            if isinstance(parsed_issue, ImplementationIssue):
                run_id = parsed_issue.orchestration.agent_run_id or ""

        snapshot = adapter.fetch_agent_run_metrics(
            run_id=run_id or f"issue-{run_issue_number}",
            association=association,
        )
        return serialize_agent_run_metrics_snapshot(snapshot)

    @app.get("/api/metrics/{repo}/implementation-issues/{issue_number}")
    def get_implementation_issue_metrics(repo: str, issue_number: int) -> dict[str, object]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        adapter = TelemetryAdapter(config=config.observability)

        # Collect all runs associated with this implementation issue via worktrees
        associations: list[dict[str, object]] = []
        run_statuses: list[str] = []
        run_starts: list[str] = []
        per_run_attempts: list[dict[str, object]] = []
        worktree_root = Path(repo_cfg.worktree_root)
        if worktree_root.exists() and worktree_root.is_dir():
            for child in sorted(worktree_root.iterdir()):
                if not (child.is_dir() and child.name.startswith("issue-")):
                    continue
                try:
                    child_issue_num = int(child.name[len("issue-"):])
                except ValueError:
                    continue
                run_state_path = child / "run-state.json"
                if run_state_path.exists():
                    try:
                        run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                        if run_state_data.get("issue_number") == issue_number:
                            assoc = run_state_data.get("telemetry_association")
                            run_id = ""
                            if isinstance(assoc, dict):
                                associations.append(assoc)
                                run_id = str(assoc.get("run_id", ""))
                            elif run_state_data.get("agent_run_id"):
                                run_id = str(run_state_data.get("agent_run_id", ""))
                            run_status = str(run_state_data.get("status", ""))
                            run_statuses.append(run_status)
                            started_at = str(run_state_data.get("started_at", ""))
                            run_starts.append(started_at)

                            per_run_attempts.append({
                                "run_id": run_id or f"attempt-{len(per_run_attempts) + 1}",
                                "status": run_status,
                                "started_at": started_at,
                                "finished_at": run_state_data.get("finished_at"),
                                "has_telemetry_association": isinstance(assoc, dict),
                            })
                    except Exception:
                        pass

        # Check if the implementation issue has been integrated (closed).
        is_integrated = False
        try:
            issue_record = issues_factory().view_issue(issue_number)
            is_integrated = issue_record.state == "closed"
        except Exception:
            pass

        snapshot = adapter.fetch_implementation_issue_metrics(
            issue_number=issue_number,
            associations=associations,
            run_statuses=run_statuses if run_statuses else None,
            is_integrated=is_integrated,
        )
        result = serialize_implementation_issue_metrics_snapshot(snapshot)
        result["runs"] = per_run_attempts
        return result

    @app.get("/api/metrics/{repo}/prd/{prd_number}")
    def get_prd_metrics(repo: str, prd_number: int) -> dict[str, object]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        adapter = TelemetryAdapter(config=config.observability)

        # Find all Implementation Issues that are children of this PRD
        gateway = issues_factory()
        if hasattr(gateway, "_cwd"):
            gateway._cwd = repo_cfg.repo_path

        try:
            issue_records = gateway.list_issues(
                state="all", labels=("implementation",)
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to list GitHub issues: {exc}"
            ) from exc

        child_snapshots: list[ImplementationIssueMetricsSnapshot] = []
        child_status_counts: dict[str, int] = {}
        worktree_root = Path(repo_cfg.worktree_root)

        for record in issue_records:
            parsed = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )
            if not isinstance(parsed, ImplementationIssue):
                continue
            if parsed.parent_prd_number != prd_number:
                continue

            # Determine child issue lifecycle status for status counts
            child_status = "unknown"
            diagnostics = getattr(parsed, "diagnostics", ())
            if diagnostics:
                child_status = "degraded"
            elif record.state == "closed":
                child_status = "succeeded"
            else:
                # Check run-state for more specific status
                issue_worktree = worktree_root / f"issue-{record.number}"
                run_state_path = issue_worktree / "run-state.json"
                if run_state_path.exists():
                    try:
                        run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                        child_status = run_state_data.get("status", "unknown")
                    except Exception:
                        child_status = "unknown"
                else:
                    if parsed.orchestration.agent_run_id or parsed.orchestration.claimed_at:
                        child_status = "claimed"
                    elif "ready-for-agent" in record.labels:
                        active_blockers = [
                            b for b in parsed.blocked_by
                            if any(
                                r.number == b and r.state == "open"
                                for r in issue_records
                            )
                        ]
                        if active_blockers:
                            child_status = "blocked"
                        else:
                            child_status = "ready"
                    else:
                        child_status = "unready"
            child_status_counts[child_status] = child_status_counts.get(child_status, 0) + 1

            # Collect all runs associated with this child implementation issue
            associations: list[dict[str, object]] = []
            run_statuses: list[str] = []
            if worktree_root.exists() and worktree_root.is_dir():
                for child_dir in sorted(worktree_root.iterdir()):
                    if not (child_dir.is_dir() and child_dir.name.startswith("issue-")):
                        continue
                    try:
                        child_issue_num = int(child_dir.name[len("issue-"):])
                    except ValueError:
                        continue
                    if child_issue_num != record.number:
                        continue
                    run_state_path = child_dir / "run-state.json"
                    if run_state_path.exists():
                        try:
                            run_state_data = json.loads(run_state_path.read_text(encoding="utf-8"))
                            if run_state_data.get("issue_number") == record.number:
                                assoc = run_state_data.get("telemetry_association")
                                if isinstance(assoc, dict):
                                    associations.append(assoc)
                                run_status = str(run_state_data.get("status", ""))
                                run_statuses.append(run_status)
                        except Exception:
                            pass

            child_snapshot = adapter.fetch_implementation_issue_metrics(
                issue_number=record.number,
                associations=associations,
                run_statuses=run_statuses if run_statuses else None,
                is_integrated=(record.state == "closed"),
            )
            child_snapshots.append(child_snapshot)

        prd_snapshot = adapter.fetch_prd_metrics(
            prd_number=prd_number,
            child_snapshots=child_snapshots,
            child_status_counts=child_status_counts,
        )
        return serialize_prd_metrics_snapshot(prd_snapshot)

    @app.get("/api/runs/{issue_number}/log")
    def get_run_log(issue_number: int, repo: str, limit: int = 100) -> dict[str, object]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        worktree_path = Path(repo_cfg.worktree_root) / f"issue-{issue_number}"
        log_path = worktree_path / "harness.log"

        if not log_path.exists():
            raise HTTPException(status_code=404, detail=f"Log file not found for issue #{issue_number}")

        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            tail_lines = lines[-limit:] if limit > 0 else lines
            content = "\n".join(tail_lines)
            return {
                "issue_number": issue_number,
                "log_path": str(log_path),
                "lines_returned": len(tail_lines),
                "content": content,
            }
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "unreadable-run-log",
                    "kind": "read-error",
                    "message": "Run log file could not be read.",
                    "issue_number": issue_number,
                    "log_path": str(log_path),
                },
            ) from exc

    @app.get("/api/repos/{repo}/implementation-issues/{issue_number}/quality-gate")
    def get_quality_gate_summary(repo: str, issue_number: int) -> dict[str, object]:
        try:
            repo_cfg = config.repo(repo)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # If quality gate is not enabled, return status "unavailable"
        if not repo_cfg.quality_gate or not repo_cfg.quality_gate.enabled:
            return {"status": "unavailable"}

        worktree_path = Path(repo_cfg.worktree_root) / f"issue-{issue_number}"
        diag_dir = worktree_path / "quality-gate"
        result_json_path = diag_dir / "result.json"

        try:
            # If worktree doesn't exist or quality-gate folder doesn't exist, return "not_run"
            if not worktree_path.exists() or not diag_dir.exists() or not diag_dir.is_dir():
                return {"status": "not_run", "message": "Quality gate has not been run."}
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "unreadable-quality-gate",
                    "kind": "read-error",
                    "message": f"Repository or worktree access failure: {exc}",
                }
            ) from exc

        # If quality-gate folder exists but result.json doesn't, return "not_run" with diagnostic message
        if not result_json_path.exists():
            return {"status": "not_run", "message": "Quality gate result.json file is missing."}

        try:
            data = json.loads(result_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"status": "invalid", "message": f"Malformed JSON in result.json: {exc}"}
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "unreadable-quality-gate",
                    "kind": "read-error",
                    "message": f"Repository or worktree access failure on result.json: {exc}",
                }
            ) from exc

        if not isinstance(data, dict):
            return {"status": "invalid", "message": "Quality gate result.json does not contain a JSON object."}

        status = data.get("status")
        if status is None:
            return {"status": "invalid", "message": "Quality gate status field is missing in result.json."}
        if status not in {"passed", "failed", "error", "not run", "not_run", "invalid", "unavailable"}:
            return {"status": "invalid", "message": f"Unrecognized Quality Gate status in result.json: {status}"}

        response = {"status": status}
        message = data.get("message")
        if isinstance(message, str) and message:
            response["message"] = message

        checks = data.get("checks")
        normalized_checks = []
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                c_id = check.get("id")
                c_name = check.get("name")
                resolved_id = str(c_id) if c_id is not None else (str(c_name) if c_name is not None else "unknown")
                resolved_name = str(c_name) if c_name is not None else (str(c_id) if c_id is not None else "unknown")
                
                c_type = check.get("type")
                resolved_type = str(c_type) if c_type is not None else None
                
                c_status = check.get("status")
                resolved_status = str(c_status) if c_status is not None else "unknown"
                
                c_advisory = check.get("advisory")
                resolved_advisory = bool(c_advisory) if c_advisory is not None else False
                
                c_msg = check.get("message")
                resolved_msg = str(c_msg) if c_msg is not None else None
                
                normalized_checks.append({
                    "id": resolved_id,
                    "name": resolved_name,
                    "type": resolved_type,
                    "status": resolved_status,
                    "advisory": resolved_advisory,
                    "message": resolved_msg
                })
        
        response["checks"] = normalized_checks

        # Judge Layer summary: read optional judge.json from the same quality-gate directory
        judge_json_path = diag_dir / "judge.json"
        if judge_json_path.exists():
            try:
                judge_data = json.loads(judge_json_path.read_text(encoding="utf-8"))
                if isinstance(judge_data, dict):
                    judge_status = judge_data.get("status")
                    judge_message = judge_data.get("message")
                    if judge_status is not None:
                        judge_summary: dict[str, object] = {"status": str(judge_status)}
                        if isinstance(judge_message, str) and judge_message:
                            judge_summary["message"] = judge_message
                        response["judge"] = judge_summary
            except (json.JSONDecodeError, OSError):
                pass

        return response

    dist_dir = Path("dashboard/dist")
    if dist_dir.exists() and dist_dir.is_dir():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return app
