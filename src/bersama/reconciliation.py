from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, TYPE_CHECKING

from bersama.github_issues import GitHubIssueRecord
from bersama.issues import (
    ClaimStatus,
    DiagnosticKind,
    GitHubIssue,
    ImplementationIssue,
    IssueKind,
    PrdIssue,
    parse_claim_status,
    parse_issue,
)

if TYPE_CHECKING:
    from bersama.discord_notifier import DiscordNotifier
    from bersama.telemetry import TelemetryAdapter


class IssueGateway(Protocol):
    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
    ) -> tuple[GitHubIssueRecord, ...]: ...
    def view_issue(self, number: int) -> GitHubIssueRecord: ...
    def add_comment(self, number: int, body: str) -> None: ...
    def add_labels(self, number: int, *labels: str) -> None: ...
    def remove_labels(self, number: int, *labels: str) -> None: ...
    def update_body(self, number: int, body: str) -> None: ...


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ReconciliationService:
    def __init__(
        self,
        *,
        issues: IssueGateway,
        stale_claim_timeout: timedelta = timedelta(hours=2),
        now_provider: callable | None = None,
        discord_notifier: DiscordNotifier | None = None,
        telemetry: TelemetryAdapter | None = None,
    ) -> None:
        self._issues = issues
        self._stale_claim_timeout = stale_claim_timeout
        self._now_provider = now_provider or _utc_now
        self._discord_notifier = discord_notifier
        self._telemetry = telemetry

    def set_discord_notifier(self, notifier: DiscordNotifier) -> None:
        """Wire a Discord notifier for PRD completion notifications."""
        self._discord_notifier = notifier

    def set_telemetry(self, telemetry: TelemetryAdapter) -> None:
        """Wire a telemetry adapter for PRD completion metrics."""
        self._telemetry = telemetry

    def reconcile(self) -> None:
        # 1. Fetch issues filtered to prd + implementation labels,
        #    with a 24h sliding window on closed issues to limit
        #    the dataset size.
        now_str = self._now_provider()
        normalized = now_str.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        now_dt = datetime.fromisoformat(normalized)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=UTC)
        else:
            now_dt = now_dt.astimezone(UTC)

        updated_since = (now_dt - timedelta(hours=24)).strftime("%Y-%m-%d")
        # Fetch open issues without time window (must see all open issues
        # for stale-claim and malformed-issue detection).
        open_records = list(
            self._issues.list_issues(
                state="open",
                labels=("prd", "implementation"),
            )
        )
        # Fetch closed issues with a 24h sliding window to limit dataset size.
        closed_records = list(
            self._issues.list_issues(
                state="closed",
                labels=("prd", "implementation"),
                updated_since=updated_since,
            )
        )
        # Deduplicate by number (open and closed fetches may overlap).
        records_by_number: dict[int, GitHubIssueRecord] = {}
        for rec in open_records + closed_records:
            records_by_number[rec.number] = rec
        records = list(records_by_number.values())

        # Parse all fetched issues
        parsed_by_number = {}
        for record in records:
            parsed_by_number[record.number] = parse_issue(
                GitHubIssue(
                    number=record.number,
                    title=record.title,
                    body=record.body,
                    labels=record.labels,
                )
            )

        for record in records:
            if record.state != "open":
                continue

            parsed = parsed_by_number[record.number]

            # C. Auto-clear orchestration metadata if user manually added ready-for-agent
            if "ready-for-agent" in record.labels:
                if isinstance(parsed, ImplementationIssue) and (parsed.orchestration.agent_run_id or parsed.orchestration.claimed_at):
                    claim_status = parse_claim_status(parsed.orchestration.claim_status)
                    if claim_status is ClaimStatus.FAILED:
                        # Failed claim with ready-for-agent is contradictory.
                        # Move to needs-triage instead of auto-clearing.
                        if "needs-triage" not in record.labels:
                            self._issues.remove_labels(record.number, "ready-for-agent")
                            self._issues.add_labels(record.number, "needs-triage")
                            self._issues.add_comment(
                                record.number,
                                f"Issue #{record.number} has a failed claim but is marked ready-for-agent. "
                                "This is a contradictory state that requires human review."
                            )
                    else:
                        from bersama.issues import upsert_section
                        # Clear Orchestration section to allow a clean new claim
                        cleared_body = upsert_section(record.body, "Orchestration", "")
                        self._issues.update_body(record.number, cleared_body)
                        self._issues.add_comment(
                            record.number,
                            f"Cleared previous claim metadata on issue #{record.number} because it was marked ready-for-agent."
                        )
                        # Re-parse this record with cleared body so that subsequent checks see it as clean!
                        parsed_by_number[record.number] = parse_issue(
                            GitHubIssue(
                                number=record.number,
                                title=record.title,
                                body=cleared_body,
                                labels=record.labels,
                            )
                        )
                        parsed = parsed_by_number[record.number]

            # A. Check for Malformed / Invalid Issues
            if parsed.diagnostics:
                is_invalid_state = any(
                    diag.kind is DiagnosticKind.INVALID_STATE
                    for diag in parsed.diagnostics
                )
                target_label = "needs-triage" if is_invalid_state else "needs-info"

                if target_label not in record.labels:
                    if "ready-for-agent" in record.labels:
                        self._issues.remove_labels(record.number, "ready-for-agent")
                    
                    self._issues.add_labels(record.number, target_label)

                    diags_text = "\n".join(f"- {diag.message}" for diag in parsed.diagnostics)
                    comment_body = (
                        f"Issue #{record.number} is malformed or in an invalid state.\n\n"
                        f"**Diagnostics:**\n{diags_text}"
                    )
                    self._issues.add_comment(record.number, comment_body)
            else:
                # If there are no diagnostics, but the issue still has "needs-info" or "needs-triage" labels,
                # remove them and restore "ready-for-agent" if applicable.
                removed_labels = []
                if "needs-info" in record.labels:
                    self._issues.remove_labels(record.number, "needs-info")
                    removed_labels.append("needs-info")
                if "needs-triage" in record.labels:
                    self._issues.remove_labels(record.number, "needs-triage")
                    removed_labels.append("needs-triage")

                if removed_labels and isinstance(parsed, ImplementationIssue) and not parsed.orchestration.claimed_at:
                    if "ready-for-agent" not in record.labels:
                        self._issues.add_labels(record.number, "ready-for-agent")
                    self._issues.add_comment(
                        record.number,
                        f"Issue #{record.number} has been resolved and is now ready for agent execution."
                    )

            # B. Check for Stale Claims
            if isinstance(parsed, ImplementationIssue) and not parsed.diagnostics:
                orchestration = parsed.orchestration
                if orchestration.claimed_at:
                    claim_status = parse_claim_status(orchestration.claim_status)
                    claimed_at_str = orchestration.claimed_at.strip()
                    if claimed_at_str.endswith("Z"):
                        claimed_at_str = claimed_at_str[:-1] + "+00:00"
                    try:
                        claimed_at_dt = datetime.fromisoformat(claimed_at_str)
                        if claimed_at_dt.tzinfo is None:
                            claimed_at_dt = claimed_at_dt.replace(tzinfo=UTC)
                        else:
                            claimed_at_dt = claimed_at_dt.astimezone(UTC)

                        is_stale = now_dt - claimed_at_dt >= self._stale_claim_timeout
                    except ValueError:
                        is_stale = True

                    if (
                        claim_status is ClaimStatus.FAILED
                        and "needs-triage" not in record.labels
                    ):
                        self._issues.add_labels(record.number, "needs-triage")
                        comment_body = (
                            f"Failed Claim Setup for issue #{record.number} requires human review.\n\n"
                            f"**Diagnostics:**\n"
                            f"- Claim Status: {orchestration.claim_status}\n"
                            f"- Claimed at: {orchestration.claimed_at}\n"
                            f"- Agent Run ID: {orchestration.agent_run_id or 'unknown'}\n"
                            f"- Implementation Branch: {orchestration.implementation_branch or 'unknown'}"
                        )
                        self._issues.add_comment(record.number, comment_body)
                    elif is_stale and "needs-triage" not in record.labels:
                        if claim_status is ClaimStatus.SETTING_UP:
                            comment_body = (
                                f"Interrupted Claim Setup detected for issue #{record.number}.\n\n"
                                f"**Diagnostics:**\n"
                                f"- Claim Status: {orchestration.claim_status}\n"
                                f"- Claimed at: {orchestration.claimed_at}\n"
                                f"- Timeout configured: {self._stale_claim_timeout}\n"
                                f"- Agent Run ID: {orchestration.agent_run_id or 'unknown'}\n"
                                f"- Implementation Branch: {orchestration.implementation_branch or 'unknown'}"
                            )
                        else:
                            comment_body = (
                                f"Claim for issue #{record.number} has become stale.\n\n"
                                f"**Diagnostics:**\n"
                                f"- Claimed at: {orchestration.claimed_at}\n"
                                f"- Timeout configured: {self._stale_claim_timeout}\n"
                                f"- Agent Run ID: {orchestration.agent_run_id or 'unknown'}"
                            )
                        self._issues.add_labels(record.number, "needs-triage")
                        self._issues.add_comment(record.number, comment_body)

            # C. Check for PRD Issue child completion (ready-for-human)
            if isinstance(parsed, PrdIssue):
                child_records = [
                    rec for rec in records
                    if isinstance(parsed_by_number.get(rec.number), ImplementationIssue)
                    and parsed_by_number[rec.number].parent_prd_number == record.number
                ]
                
                if child_records and all(rec.state == "closed" for rec in child_records):
                    if "ready-for-human" not in record.labels:
                        self._issues.add_labels(record.number, "ready-for-human")
                        # Send Discord notification with telemetry metrics if configured
                        self._send_prd_completion_notification(
                            record, child_records, parsed_by_number
                        )

    def _send_prd_completion_notification(
        self,
        prd_record: GitHubIssueRecord,
        child_records: list[GitHubIssueRecord],
        parsed_by_number: dict[int, object],
    ) -> None:
        """Send a Discord notification when all child issues of a PRD are completed.

        Fetches PRD-level execution metrics via the telemetry adapter if available.
        Falls back gracefully when telemetry is disabled or unavailable.
        """
        if self._discord_notifier is None:
            return

        # Build metrics fields from telemetry
        fields = self._build_prd_metrics_fields(child_records, parsed_by_number)

        # Build description
        child_numbers = sorted(rec.number for rec in child_records)
        child_list = ", ".join(f"#{n}" for n in child_numbers)
        description = (
            f"PRD #{prd_record.number} has all child issues completed "
            f"and is ready for human review.\n\n"
            f"**Completed Issues:** {child_list}"
        )

        self._discord_notifier.send(
            title="All Issues Completed",
            description=description,
            color=0x00FF00,  # Green
            fields=fields,
        )

    def _build_prd_metrics_fields(
        self,
        child_records: list[GitHubIssueRecord],
        parsed_by_number: dict[int, object],
    ) -> list[dict[str, object]]:
        """Build Discord embed fields with PRD-level execution metrics.

        Fetches telemetry for each child implementation issue that has an
        Agent Run ID.  Returns a list of Discord embed field dicts.
        """
        fields: list[dict[str, object]] = []

        if self._telemetry is None:
            return fields

        # Collect metrics from child runs
        total_runs = 0
        total_tokens = 0
        total_cost = 0.0
        latencies: list[float] = []
        runs_with_telemetry = 0
        runs_without_telemetry = 0

        for child_record in child_records:
            parsed = parsed_by_number.get(child_record.number)
            if not isinstance(parsed, ImplementationIssue):
                continue

            agent_run_id = parsed.orchestration.agent_run_id
            if not agent_run_id:
                continue

            total_runs += 1
            snapshot = self._telemetry.fetch_agent_run_metrics(run_id=agent_run_id)

            if snapshot.metrics_available:
                runs_with_telemetry += 1
                if snapshot.total_tokens is not None:
                    total_tokens += snapshot.total_tokens
                if snapshot.model_cost is not None:
                    total_cost += snapshot.model_cost
                if snapshot.avg_latency_ms is not None:
                    latencies.append(snapshot.avg_latency_ms)
            else:
                runs_without_telemetry += 1

        # Build fields based on what we have
        fields.append({
            "name": "Total Runs",
            "value": str(total_runs),
            "inline": True,
        })

        if runs_with_telemetry > 0:
            fields.append({
                "name": "Total Tokens",
                "value": f"{total_tokens:,}",
                "inline": True,
            })
            fields.append({
                "name": "Total Cost",
                "value": f"${total_cost:.4f}",
                "inline": True,
            })
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                fields.append({
                    "name": "Avg Latency",
                    "value": f"{avg_latency:.0f} ms",
                    "inline": True,
                })
        else:
            fields.append({
                "name": "Telemetry",
                "value": "Unavailable — no telemetry data found for any run.",
                "inline": False,
            })

        return fields
