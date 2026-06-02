"""Tests for the telemetry adapter module and dashboard metrics endpoints."""

import json
from pathlib import Path

from bersama.config import AppConfig, HarnessConfig, ObservabilityConfig, RepoConfig
from bersama.dashboard import create_dashboard_app
from bersama.github_issues import GitHubIssueRecord
from fastapi.testclient import TestClient

from bersama.telemetry import (
    AgentRunMetricsSnapshot,
    ImplementationIssueMetricsSnapshot,
    TelemetryAdapter,
    TelemetryDiagnostic,
    TelemetryDiagnosticCode,
    _normalise_agent_run_metrics,
    _aggregate_implementation_issue_metrics,
    serialize_agent_run_metrics_snapshot,
    serialize_implementation_issue_metrics_snapshot,
)


def build_config(*, observability_enabled: bool = True) -> AppConfig:
    return AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=Path("/worktrees/demo"),
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=observability_enabled,
            session_prefix="bersama",
            url="http://observability:8080" if observability_enabled else None,
            token="test-token" if observability_enabled else None,
        ),
    )


# ---- Telemetry Adapter unit tests ----


class FakeResponse:
    def __init__(self, status: int = 200, body: object = None) -> None:
        self.status = status
        self._body = body

    def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeFetcher:
    def __init__(self, response: FakeResponse | None = None, should_raise: bool = False) -> None:
        self._response = response
        self._should_raise = should_raise
        self.calls: list[str] = []

    def get(self, path: str) -> FakeResponse:
        self.calls.append(path)
        if self._should_raise:
            raise RuntimeError("Connection refused")
        return self._response or FakeResponse()


def test_adapter_returns_unconfigured_diagnostic_when_observability_disabled() -> None:
    config = ObservabilityConfig(enabled=False)
    adapter = TelemetryAdapter(config=config)

    snapshot = adapter.fetch_agent_run_metrics(run_id="run-1")

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY


def test_adapter_returns_unconfigured_diagnostic_when_url_missing() -> None:
    config = ObservabilityConfig(enabled=True, url=None)
    adapter = TelemetryAdapter(config=config)

    snapshot = adapter.fetch_agent_run_metrics(run_id="run-1")

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY


def test_adapter_returns_missing_association_diagnostic_when_association_is_none() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(config=config)

    snapshot = adapter.fetch_agent_run_metrics(run_id="run-1", association=None)

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.MISSING_ASSOCIATION


def test_adapter_returns_missing_session_diagnostic_when_run_id_missing_from_association() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(config=config)

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="", association={"repo": "demo", "parent_prd": 123}
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.MISSING_SESSION


def test_adapter_returns_missing_session_diagnostic_when_observability_returns_404() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(response=FakeResponse(status=404)),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.MISSING_SESSION
    assert "run-1" in snapshot.diagnostics[0].message


def test_adapter_returns_unreadable_diagnostic_when_observability_returns_non_200() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(response=FakeResponse(status=500)),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNREADABLE_RESPONSE


def test_adapter_returns_unreadable_diagnostic_when_connection_fails() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(should_raise=True),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNREADABLE_RESPONSE


def test_adapter_returns_unreadable_diagnostic_when_response_body_is_not_json() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")

    class BadBodyResponse(FakeResponse):
        def json(self) -> object:
            raise ValueError("not json")

    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(response=BadBodyResponse(status=200)),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNREADABLE_RESPONSE


def test_adapter_returns_unreadable_diagnostic_when_response_is_not_a_dict() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(
            response=FakeResponse(status=200, body=["not", "a", "dict"])
        ),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert not snapshot.metrics_available
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.UNREADABLE_RESPONSE


def test_adapter_returns_metrics_snapshot_when_observability_succeeds() -> None:
    config = ObservabilityConfig(enabled=True, url="http://localhost:8080", token="test")
    raw_metrics = {
        "model_usage": {
            "input_tokens": 1500,
            "output_tokens": 800,
            "cache_read_tokens": 200,
            "cache_write_tokens": 100,
            "total_tokens": 2600,
            "model_cost": 0.015,
        },
        "tool_metrics": {
            "call_count": 12,
            "error_count": 1,
        },
        "model": "claude-sonnet-4",
        "provider": "anthropic",
        "responsiveness": {
            "average": {
                "time_to_first_token_ms": 450.0,
                "latency_ms": 1200.0,
                "output_tokens_per_sec": 85.5,
            },
            "latest": {
                "time_to_first_token_ms": 320.0,
                "latency_ms": 980.0,
                "output_tokens_per_sec": 92.0,
            },
        },
        "error_count": 2,
        "latest_telemetry_at": "2026-06-02T16:24:30Z",
    }
    adapter = TelemetryAdapter(
        config=config,
        fetcher_factory=lambda: FakeFetcher(
            response=FakeResponse(status=200, body=raw_metrics)
        ),
    )

    snapshot = adapter.fetch_agent_run_metrics(
        run_id="run-1",
        association={"repo": "demo", "parent_prd": 123, "issue": 125, "run_id": "run-1"},
    )

    assert snapshot.metrics_available
    assert len(snapshot.diagnostics) == 0
    assert snapshot.run_id == "run-1"
    assert snapshot.input_tokens == 1500
    assert snapshot.output_tokens == 800
    assert snapshot.cache_read_tokens == 200
    assert snapshot.cache_write_tokens == 100
    assert snapshot.total_tokens == 2600
    assert snapshot.model_cost == 0.015
    assert snapshot.tool_call_count == 12
    assert snapshot.tool_error_count == 1
    assert snapshot.model == "claude-sonnet-4"
    assert snapshot.provider == "anthropic"
    assert snapshot.avg_time_to_first_token_ms == 450.0
    assert snapshot.avg_latency_ms == 1200.0
    assert snapshot.avg_output_tokens_per_sec == 85.5
    assert snapshot.latest_time_to_first_token_ms == 320.0
    assert snapshot.latest_latency_ms == 980.0
    assert snapshot.latest_output_tokens_per_sec == 92.0
    assert snapshot.error_count == 2
    assert snapshot.latest_telemetry_at == "2026-06-02T16:24:30Z"


# ---- Normalisation unit tests ----


def test_normalise_agent_run_metrics_handles_partial_data() -> None:
    snapshot = _normalise_agent_run_metrics(
        run_id="run-1",
        raw={"model_usage": {"input_tokens": 100}},
    )

    assert snapshot.metrics_available
    assert snapshot.input_tokens == 100
    assert snapshot.output_tokens is None
    assert snapshot.tool_call_count is None
    assert snapshot.model is None


def test_normalise_agent_run_metrics_handles_empty_data() -> None:
    snapshot = _normalise_agent_run_metrics(run_id="run-1", raw={})

    assert snapshot.metrics_available
    assert snapshot.input_tokens is None
    assert snapshot.output_tokens is None


def test_normalise_agent_run_metrics_handles_error_count_and_latest_telemetry_at() -> None:
    """Acceptance criteria: Run Metrics include error_count and latest_telemetry_at."""
    snapshot = _normalise_agent_run_metrics(
        run_id="run-1",
        raw={
            "model_usage": {"input_tokens": 500},
            "error_count": 3,
            "latest_telemetry_at": "2026-06-02T16:24:30Z",
        },
    )

    assert snapshot.metrics_available
    assert snapshot.error_count == 3
    assert snapshot.latest_telemetry_at == "2026-06-02T16:24:30Z"
    assert snapshot.input_tokens == 500


# ---- Aggregation unit tests ----


def test_aggregate_implementation_issue_metrics_empty_runs() -> None:
    snapshot = _aggregate_implementation_issue_metrics(
        issue_number=125,
        run_snapshots=[],
    )

    assert not snapshot.metrics_available
    assert snapshot.run_count == 0
    assert snapshot.runs_with_telemetry == 0
    assert snapshot.runs_without_telemetry == 0


def test_aggregate_implementation_issue_metrics_with_telemetry() -> None:
    run1 = AgentRunMetricsSnapshot(
        run_id="run-1",
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        avg_time_to_first_token_ms=400.0,
        avg_latency_ms=1000.0,
    )
    run2 = AgentRunMetricsSnapshot(
        run_id="run-2",
        input_tokens=2000,
        output_tokens=1000,
        total_tokens=3000,
        avg_time_to_first_token_ms=600.0,
        avg_latency_ms=1500.0,
    )

    snapshot = _aggregate_implementation_issue_metrics(
        issue_number=125,
        run_snapshots=[run1, run2],
    )

    assert snapshot.metrics_available
    assert snapshot.issue_number == 125
    assert snapshot.run_count == 2
    assert snapshot.successful_run_count == 2
    assert snapshot.runs_with_telemetry == 2
    assert snapshot.runs_without_telemetry == 0
    assert snapshot.input_tokens == 3000
    assert snapshot.output_tokens == 1500
    assert snapshot.total_tokens == 4500
    assert snapshot.avg_time_to_first_token_ms == 500.0  # average of 400 and 600
    assert snapshot.avg_latency_ms == 1250.0  # average of 1000 and 1500


def test_aggregate_implementation_issue_metrics_mixed_telemetry() -> None:
    run_with_telemetry = AgentRunMetricsSnapshot(
        run_id="run-1",
        input_tokens=1000,
        output_tokens=500,
    )
    run_without_telemetry = AgentRunMetricsSnapshot(
        run_id="run-2",
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                message="No association found.",
            )
        ],
    )

    snapshot = _aggregate_implementation_issue_metrics(
        issue_number=125,
        run_snapshots=[run_with_telemetry, run_without_telemetry],
    )

    assert snapshot.metrics_available
    assert snapshot.run_count == 2
    assert snapshot.runs_with_telemetry == 1
    assert snapshot.runs_without_telemetry == 1
    assert snapshot.input_tokens == 1000
    # Diagnostics from the failed run are included
    assert len(snapshot.diagnostics) == 1
    assert snapshot.diagnostics[0].code == TelemetryDiagnosticCode.MISSING_ASSOCIATION


def test_aggregate_implementation_issue_metrics_all_without_telemetry() -> None:
    run1 = AgentRunMetricsSnapshot(
        run_id="run-1",
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                message="No association found.",
            )
        ],
    )
    run2 = AgentRunMetricsSnapshot(
        run_id="run-2",
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY,
                message="Observability not configured.",
            )
        ],
    )

    snapshot = _aggregate_implementation_issue_metrics(
        issue_number=125,
        run_snapshots=[run1, run2],
    )

    assert not snapshot.metrics_available
    assert snapshot.run_count == 2
    assert snapshot.runs_with_telemetry == 0
    assert snapshot.runs_without_telemetry == 2
    assert len(snapshot.diagnostics) == 2


# ---- Serialisation tests ----


def test_serialize_agent_run_metrics_snapshot_with_diagnostics() -> None:
    snapshot = AgentRunMetricsSnapshot(
        run_id="run-1",
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                message="No association found.",
            )
        ],
    )

    result = serialize_agent_run_metrics_snapshot(snapshot)

    assert result["run_id"] == "run-1"
    assert result["metrics_available"] is False
    assert len(result["diagnostics"]) == 1
    assert result["diagnostics"][0]["code"] == "missing_association"
    assert result["diagnostics"][0]["severity"] == "warning"
    assert result["diagnostics"][0]["message"] == "No association found."
    # No raw telemetry exposed
    assert "input_tokens" not in result


def test_serialize_agent_run_metrics_snapshot_with_metrics() -> None:
    snapshot = AgentRunMetricsSnapshot(
        run_id="run-1",
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        model_cost=0.01,
        tool_call_count=5,
        tool_error_count=0,
        model="claude-sonnet-4",
        provider="anthropic",
        avg_time_to_first_token_ms=450.0,
        avg_latency_ms=1200.0,
        avg_output_tokens_per_sec=85.5,
        error_count=2,
        latest_telemetry_at="2026-06-02T16:24:30Z",
    )

    result = serialize_agent_run_metrics_snapshot(snapshot)

    assert result["metrics_available"] is True
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500
    assert result["total_tokens"] == 1500
    assert result["model_cost"] == 0.01
    assert result["tool_call_count"] == 5
    assert result["tool_error_count"] == 0
    assert result["model"] == "claude-sonnet-4"
    assert result["provider"] == "anthropic"
    assert result["error_count"] == 2
    assert result["latest_telemetry_at"] == "2026-06-02T16:24:30Z"
    # No observability credentials exposed
    assert "token" not in result
    assert "url" not in result


def test_serialize_implementation_issue_metrics_snapshot() -> None:
    snapshot = ImplementationIssueMetricsSnapshot(
        issue_number=125,
        run_count=3,
        successful_run_count=2,
        runs_with_telemetry=2,
        runs_without_telemetry=1,
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                message="No association found.",
            )
        ],
        input_tokens=5000,
        output_tokens=2500,
        avg_time_to_first_token_ms=500.0,
    )

    result = serialize_implementation_issue_metrics_snapshot(snapshot)

    assert result["issue_number"] == 125
    assert result["metrics_available"] is True
    assert result["run_count"] == 3
    assert result["successful_run_count"] == 2
    assert result["runs_with_telemetry"] == 2
    assert result["runs_without_telemetry"] == 1
    assert result["input_tokens"] == 5000
    assert result["output_tokens"] == 2500
    assert len(result["diagnostics"]) == 1


# ---- Dashboard metrics endpoint tests ----


class CustomFakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue.number: issue for issue in issues}

    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
    ) -> list[GitHubIssueRecord]:
        result = list(self.issues.values())
        if labels is not None:
            label_set = set(labels)
            result = [r for r in result if set(r.labels) & label_set]
        if state != "all":
            result = [r for r in result if r.state == state]
        return result

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self.issues[number]


def _build_claimed_issue() -> GitHubIssueRecord:
    return GitHubIssueRecord(
        number=125,
        title="Show missing telemetry diagnostics in the issue drawer",
        body=(
            "## Parent PRD\n"
            "#123\n\n"
            "## What to Build\n"
            "Add the first dashboard telemetry proxy path.\n\n"
            "## Acceptance Criteria\n"
            "- [ ] Done.\n\n"
            "## Blocked By\n"
            "None\n\n"
            "## Orchestration\n"
            "- Agent Run: run-125\n"
            "- Claimed At: 2026-06-02T16:14:30Z\n"
            "- Implementation Branch: impl/123/125-show-missing-telemetry\n"
        ),
        labels=("implementation",),
        state="open",
    )


def test_get_run_metrics_endpoint_returns_diagnostics_when_no_run_state(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    worktree_root.mkdir(parents=True)
    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    issue_gateway = CustomFakeIssueGateway(_build_claimed_issue())
    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: issue_gateway,
    )

    response = TestClient(app).get("/api/metrics/demo/runs/125")

    assert response.status_code == 200
    data = response.json()
    assert data["metrics_available"] is False
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["code"] == "missing_association"


def test_get_run_metrics_endpoint_returns_missing_association_for_run_without_telemetry_association(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-125"
    issue_worktree.mkdir(parents=True)

    run_state = {
        "status": "running",
        "issue_number": 125,
        "prd_branch": "prd/123",
        "implementation_branch": "impl/123/125",
        "started_at": "2026-06-02T16:14:45Z",
        # No telemetry_association
    }
    (issue_worktree / "run-state.json").write_text(json.dumps(run_state))

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    app = create_dashboard_app(config=config)

    response = TestClient(app).get("/api/metrics/demo/runs/125")

    assert response.status_code == 200
    data = response.json()
    assert data["metrics_available"] is False
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["code"] == "missing_association"


def test_get_run_metrics_endpoint_uses_telemetry_association_from_run_state(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-125"
    issue_worktree.mkdir(parents=True)

    run_state = {
        "status": "running",
        "issue_number": 125,
        "prd_branch": "prd/123",
        "implementation_branch": "impl/123/125",
        "started_at": "2026-06-02T16:14:45Z",
        "telemetry_association": {
            "repo": "demo",
            "parent_prd": 123,
            "issue": 125,
            "run_id": "run-125",
        },
    }
    (issue_worktree / "run-state.json").write_text(json.dumps(run_state))

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    app = create_dashboard_app(config=config)

    response = TestClient(app).get("/api/metrics/demo/runs/125")

    assert response.status_code == 200
    data = response.json()
    # Since there's no actual observability server, this will be a connection error
    assert data["metrics_available"] is False
    assert data["diagnostics"][0]["code"] == "unreadable_response"


def test_get_implementation_issue_metrics_endpoint_handles_no_worktree(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    worktree_root.mkdir(parents=True)
    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    app = create_dashboard_app(config=config)

    response = TestClient(app).get("/api/metrics/demo/implementation-issues/125")

    assert response.status_code == 200
    data = response.json()
    assert data["metrics_available"] is False
    assert data["issue_number"] == 125
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["code"] == "missing_association"


def test_metrics_endpoints_are_not_found_for_unknown_repo() -> None:
    app = create_dashboard_app(config=build_config(observability_enabled=True))

    response = TestClient(app).get("/api/metrics/missing/runs/1")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Unknown repo 'missing'. Available repos: demo."
    }


# ---- Telemetry diagnostics in issues endpoint ----


def test_issues_endpoint_includes_telemetry_diagnostics_for_enabled_observability(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-125"
    issue_worktree.mkdir(parents=True)

    run_state = {
        "status": "running",
        "issue_number": 125,
        "prd_branch": "prd/123",
        "implementation_branch": "impl/123/125",
        "started_at": "2026-06-02T16:14:45Z",
        # No telemetry_association
    }
    (issue_worktree / "run-state.json").write_text(json.dumps(run_state))

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    prd_issue = GitHubIssueRecord(
        number=123,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )

    class FakeGateway(CustomFakeIssueGateway):
        def list_issues(self, **kwargs) -> list[GitHubIssueRecord]:
            return [prd_issue, _build_claimed_issue()]

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: FakeGateway(prd_issue, _build_claimed_issue()),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    issues = response.json()

    # PRD should have children
    assert len(issues) == 1
    assert issues[0]["kind"] == "prd"
    assert len(issues[0]["children"]) == 1

    child = issues[0]["children"][0]
    assert child["number"] == 125
    assert child["kind"] == "implementation"
    # Telemetry diagnostics should be present even though observability is configured but
    # association is missing
    assert child["telemetry_diagnostics"] is not None
    assert len(child["telemetry_diagnostics"]) == 1
    assert child["telemetry_diagnostics"][0]["code"] == "missing_association"
    # Lifecycle status is unchanged
    assert child["status"] == "running"


def test_issues_endpoint_does_not_include_telemetry_diagnostics_when_observability_disabled(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-125"
    issue_worktree.mkdir(parents=True)

    run_state = {
        "status": "running",
        "issue_number": 125,
        "prd_branch": "prd/123",
        "implementation_branch": "impl/123/125",
        "started_at": "2026-06-02T16:14:45Z",
    }
    (issue_worktree / "run-state.json").write_text(json.dumps(run_state))

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(enabled=False),
    )

    prd_issue = GitHubIssueRecord(
        number=123,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )

    class FakeGateway(CustomFakeIssueGateway):
        def list_issues(self, **kwargs) -> list[GitHubIssueRecord]:
            return [prd_issue, _build_claimed_issue()]

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: FakeGateway(prd_issue, _build_claimed_issue()),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    child = response.json()[0]["children"][0]
    assert child["telemetry_diagnostics"] is None


def test_issues_endpoint_telemetry_diagnostics_with_association_no_diagnostics(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path / "worktrees" / "demo"
    issue_worktree = worktree_root / "issue-125"
    issue_worktree.mkdir(parents=True)

    run_state = {
        "status": "running",
        "issue_number": 125,
        "prd_branch": "prd/123",
        "implementation_branch": "impl/123/125",
        "started_at": "2026-06-02T16:14:45Z",
        "telemetry_association": {
            "repo": "demo",
            "parent_prd": 123,
            "issue": 125,
            "run_id": "run-125",
        },
    }
    (issue_worktree / "run-state.json").write_text(json.dumps(run_state))

    config = AppConfig(
        repos={
            "demo": RepoConfig(
                name="demo",
                repo_path=Path("/repos/demo"),
                main_branch="main",
                worktree_root=worktree_root,
                global_concurrency=1,
                per_prd_concurrency=1,
                default_harness="local",
            )
        },
        harnesses={
            "local": HarnessConfig(
                name="local",
                command="codex",
                args_template=(),
            )
        },
        observability=ObservabilityConfig(
            enabled=True,
            url="http://localhost:8080",
            token="test-token",
        ),
    )

    prd_issue = GitHubIssueRecord(
        number=123,
        title="PRD Title",
        body="Some PRD.",
        labels=("prd",),
        state="open",
    )

    class FakeGateway(CustomFakeIssueGateway):
        def list_issues(self, **kwargs) -> list[GitHubIssueRecord]:
            return [prd_issue, _build_claimed_issue()]

    app = create_dashboard_app(
        config=config,
        issue_gateway_factory=lambda: FakeGateway(prd_issue, _build_claimed_issue()),
    )

    response = TestClient(app).get("/api/issues?repo=demo")

    assert response.status_code == 200
    child = response.json()[0]["children"][0]
    # Association exists, so no diagnostics from the issues endpoint
    assert child["telemetry_diagnostics"] is None
    # Lifecycle status is unchanged
    assert child["status"] == "running"


def test_telemetry_diagnostics_do_not_change_lifecycle_status() -> None:
    """Acceptance criteria: Missing telemetry does not change lifecycle status."""
    snapshot = AgentRunMetricsSnapshot(
        run_id="run-1",
        diagnostics=[
            TelemetryDiagnostic(
                code=TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY,
                message="Observability not configured.",
            )
        ],
    )

    # The snapshot carries diagnostics, not a "failed" status
    assert not snapshot.metrics_available
    # Run status would come from Bersama lifecycle, not from telemetry
    # This test verifies that the telemetry module does not emit lifecycle status
    assert not hasattr(snapshot, "status")


def test_observability_credentials_not_exposed_in_serialized_output() -> None:
    """Acceptance criteria: Observability credentials are not exposed to browser."""
    snapshot = AgentRunMetricsSnapshot(
        run_id="run-1",
        input_tokens=1000,
    )

    result = serialize_agent_run_metrics_snapshot(snapshot)

    # Check that no credential-like keys are present
    assert "token" not in result
    assert "url" not in result
    assert "observability" not in result
    assert "auth" not in result
