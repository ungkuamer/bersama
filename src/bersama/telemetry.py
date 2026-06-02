"""Telemetry adapter for proxying Execution Telemetry from pi-agent-observability.

This module joins Bersama lifecycle state and pi-agent-observability telemetry
through explicit Run Telemetry Associations. It produces dashboard-shaped metrics
snapshots on demand and surfaces Telemetry Diagnostics when telemetry is
unavailable instead of treating missing telemetry as an Agent Run failure.

Observability credentials and raw pi-agent-observability event shapes MUST NOT
be exposed through any public interface of this module.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Protocol

from bersama.config import ObservabilityConfig


class TelemetryDiagnosticCode(Enum):
    MISSING_ASSOCIATION = "missing_association"
    MISSING_SESSION = "missing_session"
    UNREADABLE_RESPONSE = "unreadable_response"
    UNCONFIGURED_OBSERVABILITY = "unconfigured_observability"


@dataclasses.dataclass(frozen=True)
class TelemetryDiagnostic:
    code: TelemetryDiagnosticCode
    message: str

    @property
    def severity(self) -> str:
        """Return a severity label suitable for dashboard rendering."""
        return "warning"


@dataclasses.dataclass(frozen=True)
class AgentRunMetricsSnapshot:
    """Dashboard-shaped metrics for a single Agent Run.

    When telemetry is unavailable the snapshot carries diagnostics instead of
    metrics.  Observability credentials and raw pi-agent-observability event
    shapes are never included in this shape.
    """
    run_id: str
    diagnostics: list[TelemetryDiagnostic] = dataclasses.field(default_factory=list)

    # Metrics available only when telemetry is present

    # Model usage (tokens and cost)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    model_cost: float | None = None

    # Tool activity
    tool_call_count: int | None = None
    tool_error_count: int | None = None

    # Model info
    model: str | None = None
    provider: str | None = None

    # Responsiveness (average)
    avg_time_to_first_token_ms: float | None = None
    avg_latency_ms: float | None = None
    avg_output_tokens_per_sec: float | None = None

    # Responsiveness (latest)
    latest_time_to_first_token_ms: float | None = None
    latest_latency_ms: float | None = None
    latest_output_tokens_per_sec: float | None = None

    # Error count (general errors, separate from tool errors)
    error_count: int | None = None

    # Latest telemetry timestamp
    latest_telemetry_at: str | None = None

    @property
    def metrics_available(self) -> bool:
        return not self.diagnostics


@dataclasses.dataclass(frozen=True)
class ImplementationIssueMetricsSnapshot:
    """Dashboard-shaped metrics aggregated across all Agent Runs for one
    Implementation Issue.
    """
    issue_number: int
    diagnostics: list[TelemetryDiagnostic] = dataclasses.field(default_factory=list)

    # Aggregated model usage
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    model_cost: float | None = None

    # Aggregated tool activity
    tool_call_count: int | None = None
    tool_error_count: int | None = None

    # Aggregated responsiveness (averaged across runs)
    avg_time_to_first_token_ms: float | None = None
    avg_latency_ms: float | None = None
    avg_output_tokens_per_sec: float | None = None

    # Summary
    run_count: int = 0
    successful_run_count: int = 0
    runs_with_telemetry: int = 0
    runs_without_telemetry: int = 0
    failure_count: int = 0
    latest_run_status: str | None = None

    @property
    def metrics_available(self) -> bool:
        return self.runs_with_telemetry > 0


@dataclasses.dataclass(frozen=True)
class PrdMetricsSnapshot:
    """Dashboard-shaped metrics aggregated across child Implementation Issues
    and their Agent Runs for one PRD Issue.
    """
    issue_number: int
    diagnostics: list[TelemetryDiagnostic] = dataclasses.field(default_factory=list)

    # Aggregated model usage
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    model_cost: float | None = None

    # Aggregated tool activity
    tool_call_count: int | None = None
    tool_error_count: int | None = None

    # Aggregated responsiveness
    avg_time_to_first_token_ms: float | None = None
    avg_latency_ms: float | None = None
    avg_output_tokens_per_sec: float | None = None

    # Summary
    implementation_issue_count: int = 0
    total_run_count: int = 0
    successful_run_count: int = 0
    runs_with_telemetry: int = 0
    runs_without_telemetry: int = 0

    @property
    def metrics_available(self) -> bool:
        return not self.diagnostics


class _Fetcher(Protocol):
    """Thin HTTP fetch protocol so tests can inject fake responses."""

    def get(self, path: str) -> _Response: ...


class _Response(Protocol):
    @property
    def status(self) -> int: ...
    def json(self) -> object: ...
    @property
    def text(self) -> str: ...


def _snapshot_from_objects(
    diagnostics: list[TelemetryDiagnostic],
    *,
    _objects: list[dict[str, object]] | None = None,
) -> AgentRunMetricsSnapshot:
    """Produce a dashboard-shaped AgentRunMetricsSnapshot from raw
    observability response objects.

    This internal helper normalises the raw pi-agent-observability event shape
    so the rest of the system never sees credential-bearing or raw event data.
    """
    snapshot = AgentRunMetricsSnapshot(
        run_id="",
        diagnostics=diagnostics,
    )
    return snapshot


class TelemetryAdapter:
    """Proxy adapter that fetches telemetry from pi-agent-observability and
    produces dashboard-shaped metrics snapshots.

    Observability credentials (URL and token) are injected at construction time
    and never exposed to callers or serialised into any returned data.
    """

    def __init__(
        self,
        *,
        config: ObservabilityConfig,
        fetcher_factory: object | None = None,
        base_url: str | None = None,
    ) -> None:
        self._config = config
        self._base_url = base_url or (config.url.rstrip("/") if config.url else None)
        self._token = config.token
        self._fetcher_factory = fetcher_factory

    def _build_fetcher(self) -> _Fetcher | None:
        if self._fetcher_factory is not None:
            fetcher = self._fetcher_factory()
            if fetcher is not None:
                return fetcher

        if not self._base_url:
            return None

        import http.client
        import urllib.parse

        base = self._base_url
        token = self._token

        class HttpFetcher:
            def get(self, path: str) -> _Response:
                parsed = urllib.parse.urlparse(base + path)
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80)
                headers: dict[str, str] = {}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                conn.request("GET", parsed.path, headers=headers)
                return conn.getresponse()  # type: ignore[return-value]

        return HttpFetcher()

    def fetch_agent_run_metrics(
        self, *, run_id: str, association: dict[str, object] | None = None
    ) -> AgentRunMetricsSnapshot:
        """Return metrics for one Agent Run, or diagnostics when telemetry is
        unavailable.
        """
        diagnostics: list[TelemetryDiagnostic] = []

        # 1. Observability not configured
        if not self._config.enabled or not self._base_url:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY,
                    message="pi-agent-observability is not configured. Set observability.enabled, "
                    "observability.url, and observability.token in your configuration.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        # 2. Missing association
        if not association:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                    message="No Run Telemetry Association found. The Agent Run did not declare "
                    "observability identity at startup.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        # 3. Attempt to fetch telemetry session
        session_id = association.get("run_id")
        if not session_id:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.MISSING_SESSION,
                    message="Run Telemetry Association is missing the run_id needed to resolve "
                    "a Telemetry Session.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        fetcher = self._build_fetcher()
        if fetcher is None:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNCONFIGURED_OBSERVABILITY,
                    message="pi-agent-observability is not configured. Set observability.enabled, "
                    "observability.url, and observability.token in your configuration.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        try:
            response = fetcher.get(f"/api/sessions/{session_id}/metrics")
        except Exception:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNREADABLE_RESPONSE,
                    message="pi-agent-observability could not be reached.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        # 4. Parse response
        try:
            status = response.status
        except Exception:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNREADABLE_RESPONSE,
                    message="pi-agent-observability returned an unreadable response.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        if status != 200:
            if status == 404:
                diagnostics.append(
                    TelemetryDiagnostic(
                        code=TelemetryDiagnosticCode.MISSING_SESSION,
                        message=f"No Telemetry Session found for run_id '{session_id}'. "
                        "The Agent Run may have completed before telemetry was stored, "
                        "or the observability server may not have received the events.",
                    )
                )
            else:
                diagnostics.append(
                    TelemetryDiagnostic(
                        code=TelemetryDiagnosticCode.UNREADABLE_RESPONSE,
                        message=f"pi-agent-observability returned HTTP {status}.",
                    )
                )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        try:
            data = response.json()
        except Exception:
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNREADABLE_RESPONSE,
                    message="pi-agent-observability returned an unreadable response body.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        if not isinstance(data, dict):
            diagnostics.append(
                TelemetryDiagnostic(
                    code=TelemetryDiagnosticCode.UNREADABLE_RESPONSE,
                    message="pi-agent-observability returned an unexpected response shape.",
                )
            )
            return AgentRunMetricsSnapshot(run_id=run_id, diagnostics=diagnostics)

        # 5. Normalise into Bersama dashboard shape
        return _normalise_agent_run_metrics(run_id=run_id, raw=data)

    def fetch_implementation_issue_metrics(
        self,
        *,
        issue_number: int,
        associations: list[dict[str, object]] | None = None,
        run_statuses: list[str] | None = None,
    ) -> ImplementationIssueMetricsSnapshot:
        """Return aggregated metrics for an Implementation Issue.

        Aggregates across all associated Agent Runs and reports diagnostics
        for runs that are missing telemetry.
        """
        if not associations:
            return ImplementationIssueMetricsSnapshot(
                issue_number=issue_number,
                diagnostics=[
                    TelemetryDiagnostic(
                        code=TelemetryDiagnosticCode.MISSING_ASSOCIATION,
                        message=f"No Agent Run associations found for Implementation Issue #{issue_number}.",
                    )
                ],
            )

        run_snapshots: list[AgentRunMetricsSnapshot] = []
        for assoc in associations:
            run_id = str(assoc.get("run_id", ""))
            snapshot = self.fetch_agent_run_metrics(run_id=run_id, association=assoc)
            run_snapshots.append(snapshot)

        return _aggregate_implementation_issue_metrics(
            issue_number=issue_number,
            run_snapshots=run_snapshots,
            run_statuses=run_statuses,
        )


def _normalise_agent_run_metrics(
    *, run_id: str, raw: dict[str, object]
) -> AgentRunMetricsSnapshot:
    """Normalise raw pi-agent-observability event data into a
    Bersama dashboard AgentRunMetricsSnapshot.

    This is the ONLY place where raw observability shapes are translated.
    """
    model_usage = raw.get("model_usage")
    if isinstance(model_usage, dict):
        input_tokens = _as_int(model_usage.get("input_tokens"))
        output_tokens = _as_int(model_usage.get("output_tokens"))
        cache_read_tokens = _as_int(model_usage.get("cache_read_tokens"))
        cache_write_tokens = _as_int(model_usage.get("cache_write_tokens"))
        total_tokens = _as_int(model_usage.get("total_tokens"))
        model_cost = _as_float(model_usage.get("model_cost"))
    else:
        input_tokens = None
        output_tokens = None
        cache_read_tokens = None
        cache_write_tokens = None
        total_tokens = None
        model_cost = None

    tool_metrics = raw.get("tool_metrics")
    if isinstance(tool_metrics, dict):
        tool_call_count = _as_int(tool_metrics.get("call_count"))
        tool_error_count = _as_int(tool_metrics.get("error_count"))
    else:
        tool_call_count = None
        tool_error_count = None

    error_count = raw.get("error_count")
    if isinstance(error_count, (int, float)):
        error_count = _as_int(error_count)
    else:
        error_count = None

    latest_telemetry_at = raw.get("latest_telemetry_at")
    if isinstance(latest_telemetry_at, str):
        latest_telemetry_at = latest_telemetry_at
    else:
        latest_telemetry_at = None

    model = raw.get("model")
    if isinstance(model, str):
        model = model
    else:
        model = None

    provider = raw.get("provider")
    if isinstance(provider, str):
        provider = provider
    else:
        provider = None

    responsiveness = raw.get("responsiveness")
    if isinstance(responsiveness, dict):
        avg = responsiveness.get("average")
        if isinstance(avg, dict):
            avg_ttf = _as_float(avg.get("time_to_first_token_ms"))
            avg_latency = _as_float(avg.get("latency_ms"))
            avg_tps = _as_float(avg.get("output_tokens_per_sec"))
        else:
            avg_ttf = None
            avg_latency = None
            avg_tps = None

        latest = responsiveness.get("latest")
        if isinstance(latest, dict):
            latest_ttf = _as_float(latest.get("time_to_first_token_ms"))
            latest_latency = _as_float(latest.get("latency_ms"))
            latest_tps = _as_float(latest.get("output_tokens_per_sec"))
        else:
            latest_ttf = None
            latest_latency = None
            latest_tps = None
    else:
        avg_ttf = None
        avg_latency = None
        avg_tps = None
        latest_ttf = None
        latest_latency = None
        latest_tps = None

    return AgentRunMetricsSnapshot(
        run_id=run_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        total_tokens=total_tokens,
        model_cost=model_cost,
        tool_call_count=tool_call_count,
        tool_error_count=tool_error_count,
        model=model,
        provider=provider,
        avg_time_to_first_token_ms=avg_ttf,
        avg_latency_ms=avg_latency,
        avg_output_tokens_per_sec=avg_tps,
        latest_time_to_first_token_ms=latest_ttf,
        latest_latency_ms=latest_latency,
        latest_output_tokens_per_sec=latest_tps,
        error_count=error_count,
        latest_telemetry_at=latest_telemetry_at,
    )


def _aggregate_implementation_issue_metrics(
    *,
    issue_number: int,
    run_snapshots: list[AgentRunMetricsSnapshot],
    run_statuses: list[str] | None = None,
) -> ImplementationIssueMetricsSnapshot:
    """Aggregate individual Agent Run snapshots into an Implementation Issue
    metrics view.
    """
    diagnostics: list[TelemetryDiagnostic] = []
    runs_with_telemetry = 0
    runs_without_telemetry = 0
    successful_runs = 0
    failure_count = 0
    latest_run_status: str | None = None

    # Collectors for numeric aggregation
    input_tokens_total = 0
    output_tokens_total = 0
    cache_read_tokens_total = 0
    cache_write_tokens_total = 0
    total_tokens_total = 0
    model_cost_total = 0.0
    tool_call_count_total = 0
    tool_error_count_total = 0
    avg_ttf_values: list[float] = []
    avg_latency_values: list[float] = []
    avg_tps_values: list[float] = []
    has_any_metrics = False

    for i, snap in enumerate(run_snapshots):
        if run_statuses is not None and i < len(run_statuses):
            status = run_statuses[i]
            if status:
                latest_run_status = status
                if status == "failed":
                    failure_count += 1

        if snap.metrics_available:
            runs_with_telemetry += 1
            has_any_metrics = True
            if snap.input_tokens is not None:
                input_tokens_total += snap.input_tokens
            if snap.output_tokens is not None:
                output_tokens_total += snap.output_tokens
            if snap.cache_read_tokens is not None:
                cache_read_tokens_total += snap.cache_read_tokens
            if snap.cache_write_tokens is not None:
                cache_write_tokens_total += snap.cache_write_tokens
            if snap.total_tokens is not None:
                total_tokens_total += snap.total_tokens
            if snap.model_cost is not None:
                model_cost_total += snap.model_cost
            if snap.tool_call_count is not None:
                tool_call_count_total += snap.tool_call_count
            if snap.tool_error_count is not None:
                tool_error_count_total += snap.tool_error_count
            if snap.avg_time_to_first_token_ms is not None:
                avg_ttf_values.append(snap.avg_time_to_first_token_ms)
            if snap.avg_latency_ms is not None:
                avg_latency_values.append(snap.avg_latency_ms)
            if snap.avg_output_tokens_per_sec is not None:
                avg_tps_values.append(snap.avg_output_tokens_per_sec)
            successful_runs += 1
        else:
            runs_without_telemetry += 1
            diagnostics.extend(snap.diagnostics)

    if not has_any_metrics:
        # No telemetry data in any run — return diagnostics (may be empty for
        # empty run lists, which still means no metrics available)
        return ImplementationIssueMetricsSnapshot(
            issue_number=issue_number,
            diagnostics=diagnostics,
            run_count=len(run_snapshots),
            successful_run_count=successful_runs,
            runs_with_telemetry=runs_with_telemetry,
            runs_without_telemetry=runs_without_telemetry,
            failure_count=failure_count,
            latest_run_status=latest_run_status,
        )

    return ImplementationIssueMetricsSnapshot(
        issue_number=issue_number,
        diagnostics=diagnostics,
        input_tokens=input_tokens_total,
        output_tokens=output_tokens_total,
        cache_read_tokens=cache_read_tokens_total,
        cache_write_tokens=cache_write_tokens_total,
        total_tokens=total_tokens_total,
        model_cost=model_cost_total,
        tool_call_count=tool_call_count_total,
        tool_error_count=tool_error_count_total,
        avg_time_to_first_token_ms=_mean(avg_ttf_values),
        avg_latency_ms=_mean(avg_latency_values),
        avg_output_tokens_per_sec=_mean(avg_tps_values),
        run_count=len(run_snapshots),
        successful_run_count=successful_runs,
        runs_with_telemetry=runs_with_telemetry,
        runs_without_telemetry=runs_without_telemetry,
        failure_count=failure_count,
        latest_run_status=latest_run_status,
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and not value != value:  # NaN check
        return int(value)
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _serialize_diagnostic(diag: TelemetryDiagnostic) -> dict[str, str]:
    return {
        "code": diag.code.value,
        "severity": diag.severity,
        "message": diag.message,
    }


def serialize_agent_run_metrics_snapshot(
    snapshot: AgentRunMetricsSnapshot,
) -> dict[str, object]:
    result: dict[str, object] = {
        "run_id": snapshot.run_id,
        "diagnostics": [_serialize_diagnostic(d) for d in snapshot.diagnostics],
        "metrics_available": snapshot.metrics_available,
    }
    if snapshot.metrics_available:
        result.update({
            "input_tokens": snapshot.input_tokens,
            "output_tokens": snapshot.output_tokens,
            "cache_read_tokens": snapshot.cache_read_tokens,
            "cache_write_tokens": snapshot.cache_write_tokens,
            "total_tokens": snapshot.total_tokens,
            "model_cost": snapshot.model_cost,
            "tool_call_count": snapshot.tool_call_count,
            "tool_error_count": snapshot.tool_error_count,
            "model": snapshot.model,
            "provider": snapshot.provider,
            "avg_time_to_first_token_ms": snapshot.avg_time_to_first_token_ms,
            "avg_latency_ms": snapshot.avg_latency_ms,
            "avg_output_tokens_per_sec": snapshot.avg_output_tokens_per_sec,
            "latest_time_to_first_token_ms": snapshot.latest_time_to_first_token_ms,
            "latest_latency_ms": snapshot.latest_latency_ms,
            "latest_output_tokens_per_sec": snapshot.latest_output_tokens_per_sec,
            "error_count": snapshot.error_count,
            "latest_telemetry_at": snapshot.latest_telemetry_at,
        })
    return result


def serialize_implementation_issue_metrics_snapshot(
    snapshot: ImplementationIssueMetricsSnapshot,
) -> dict[str, object]:
    result: dict[str, object] = {
        "issue_number": snapshot.issue_number,
        "diagnostics": [_serialize_diagnostic(d) for d in snapshot.diagnostics],
        "metrics_available": snapshot.metrics_available,
        "run_count": snapshot.run_count,
        "successful_run_count": snapshot.successful_run_count,
        "runs_with_telemetry": snapshot.runs_with_telemetry,
        "runs_without_telemetry": snapshot.runs_without_telemetry,
        "failure_count": snapshot.failure_count,
        "latest_run_status": snapshot.latest_run_status,
    }
    if snapshot.metrics_available or snapshot.run_count > 0:
        result.update({
            "input_tokens": snapshot.input_tokens,
            "output_tokens": snapshot.output_tokens,
            "cache_read_tokens": snapshot.cache_read_tokens,
            "cache_write_tokens": snapshot.cache_write_tokens,
            "total_tokens": snapshot.total_tokens,
            "model_cost": snapshot.model_cost,
            "tool_call_count": snapshot.tool_call_count,
            "tool_error_count": snapshot.tool_error_count,
            "avg_time_to_first_token_ms": snapshot.avg_time_to_first_token_ms,
            "avg_latency_ms": snapshot.avg_latency_ms,
            "avg_output_tokens_per_sec": snapshot.avg_output_tokens_per_sec,
        })
    return result
