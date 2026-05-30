from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from bersama.github_issues import GitHubIssueRecord
from bersama.issues import (
    Diagnostic,
    DiagnosticKind,
    GitHubIssue,
    ImplementationIssue,
    IssueKind,
    ParsedIssue,
    PrdIssue,
    parse_issue,
)


class PlannerDecisionKind(Enum):
    CLAIMABLE = "claimable"
    ACTIVE_CLAIM = "active-claim"
    STALE_CLAIM = "stale-claim"
    BLOCKED = "blocked"
    PENDING_CONCURRENCY = "pending-concurrency"
    NEEDS_INFO = "needs-info"
    NEEDS_TRIAGE = "needs-triage"
    UNREADY = "unready"
    CLOSED = "closed"


@dataclass(frozen=True)
class PlannerIssueDecision:
    issue_number: int
    kind: PlannerDecisionKind
    diagnostics: tuple[Diagnostic, ...] = ()
    blocking_issue_numbers: tuple[int, ...] = ()


@dataclass(frozen=True)
class PlannerResult:
    decisions: tuple[PlannerIssueDecision, ...]

    @property
    def claimable_issue_numbers(self) -> tuple[int, ...]:
        return tuple(
            decision.issue_number
            for decision in self.decisions
            if decision.kind is PlannerDecisionKind.CLAIMABLE
        )


def plan_issue_actions(
    issue_records: tuple[GitHubIssueRecord, ...],
    *,
    global_concurrency: int,
    per_prd_concurrency: int,
    stale_claim_timeout: timedelta,
    now: datetime,
    active_agent_run_issue_numbers: frozenset[int] = frozenset(),
) -> PlannerResult:
    issue_records_by_number = {record.number: record for record in issue_records}
    parsed_by_number = {
        record.number: _parse_issue_record(record) for record in issue_records
    }
    active_claims_by_prd, unassigned_in_memory = _count_active_claims_by_prd(
        parsed_by_number,
        issue_records_by_number,
        stale_claim_timeout=stale_claim_timeout,
        now=now,
        active_agent_run_issue_numbers=active_agent_run_issue_numbers,
    )
    global_slots = max(0, global_concurrency - sum(active_claims_by_prd.values()) - unassigned_in_memory)
    remaining_prd_slots = {
        prd_number: max(0, per_prd_concurrency - count)
        for prd_number, count in active_claims_by_prd.items()
    }

    decisions: list[PlannerIssueDecision] = []
    eligible_for_claim: list[ImplementationIssue] = []

    for record in sorted(issue_records, key=lambda item: item.number):
        parsed = parsed_by_number[record.number]
        decision = _base_decision_for_issue(
            record,
            parsed,
            parsed_by_number,
            issue_records_by_number,
            stale_claim_timeout=stale_claim_timeout,
            now=now,
        )
        if decision is None:
            if isinstance(parsed, ImplementationIssue):
                eligible_for_claim.append(parsed)
            continue
        decisions.append(decision)

    for issue in eligible_for_claim:
        assert issue.parent_prd_number is not None
        prd_slots = remaining_prd_slots.get(issue.parent_prd_number, per_prd_concurrency)
        if global_slots > 0 and prd_slots > 0:
            decisions.append(
                PlannerIssueDecision(
                    issue_number=issue.issue.number,
                    kind=PlannerDecisionKind.CLAIMABLE,
                )
            )
            global_slots -= 1
            remaining_prd_slots[issue.parent_prd_number] = prd_slots - 1
            continue

        decisions.append(
            PlannerIssueDecision(
                issue_number=issue.issue.number,
                kind=PlannerDecisionKind.PENDING_CONCURRENCY,
            )
        )

    decisions.sort(key=lambda item: item.issue_number)
    return PlannerResult(decisions=tuple(decisions))


def _base_decision_for_issue(
    record: GitHubIssueRecord,
    parsed: ParsedIssue,
    parsed_by_number: dict[int, ParsedIssue],
    issue_records_by_number: dict[int, GitHubIssueRecord],
    *,
    stale_claim_timeout: timedelta,
    now: datetime,
) -> PlannerIssueDecision | None:
    if record.state != "open":
        if parsed.kind is IssueKind.IMPLEMENTATION:
            return PlannerIssueDecision(
                issue_number=record.number,
                kind=PlannerDecisionKind.CLOSED,
            )
        return None

    if "ready-for-agent" in record.labels and parsed.kind is not IssueKind.IMPLEMENTATION:
        return PlannerIssueDecision(
            issue_number=record.number,
            kind=PlannerDecisionKind.NEEDS_TRIAGE,
            diagnostics=(
                Diagnostic(
                    code="ready-label-on-non-implementation",
                    kind=DiagnosticKind.INVALID_STATE,
                    message="ready-for-agent can only be used on Implementation Issues.",
                ),
            ),
        )

    if not isinstance(parsed, ImplementationIssue):
        return None

    if parsed.diagnostics:
        decision_kind = PlannerDecisionKind.NEEDS_INFO
        if any(diagnostic.kind is DiagnosticKind.INVALID_STATE for diagnostic in parsed.diagnostics):
            decision_kind = PlannerDecisionKind.NEEDS_TRIAGE
        return PlannerIssueDecision(
            issue_number=record.number,
            kind=decision_kind,
            diagnostics=parsed.diagnostics,
        )

    if _has_claim_metadata(parsed):
        if "ready-for-agent" in record.labels:
            return PlannerIssueDecision(
                issue_number=record.number,
                kind=PlannerDecisionKind.NEEDS_TRIAGE,
                diagnostics=(
                    Diagnostic(
                        code="claimed-issue-still-ready",
                        kind=DiagnosticKind.INVALID_STATE,
                        message="Claimed Implementation Issue still has ready-for-agent.",
                    ),
                ),
            )

        if _is_stale_claim(parsed, stale_claim_timeout=stale_claim_timeout, now=now):
            return PlannerIssueDecision(
                issue_number=record.number,
                kind=PlannerDecisionKind.STALE_CLAIM,
                diagnostics=(
                    Diagnostic(
                        code="stale-claim",
                        kind=DiagnosticKind.INVALID_STATE,
                        message="Claim metadata is older than the configured stale claim timeout.",
                    ),
                ),
            )

        return PlannerIssueDecision(
            issue_number=record.number,
            kind=PlannerDecisionKind.ACTIVE_CLAIM,
        )

    if "ready-for-agent" not in record.labels:
        return PlannerIssueDecision(
            issue_number=record.number,
            kind=PlannerDecisionKind.UNREADY,
        )

    dependency_diagnostics = _validate_dependencies(parsed, parsed_by_number)
    if dependency_diagnostics:
        return PlannerIssueDecision(
            issue_number=record.number,
            kind=PlannerDecisionKind.NEEDS_TRIAGE,
            diagnostics=dependency_diagnostics,
        )

    open_blockers = tuple(
        blocker_number
        for blocker_number in parsed.blocked_by
        if _is_open_implementation_issue(
            parsed_by_number.get(blocker_number),
            issue_records_by_number.get(blocker_number),
        )
    )
    if open_blockers:
        return PlannerIssueDecision(
            issue_number=record.number,
            kind=PlannerDecisionKind.BLOCKED,
            blocking_issue_numbers=open_blockers,
        )

    return None


def _parse_issue_record(record: GitHubIssueRecord) -> ParsedIssue:
    return parse_issue(
        GitHubIssue(
            number=record.number,
            title=record.title,
            body=record.body,
            labels=record.labels,
        )
    )


def _count_active_claims_by_prd(
    parsed_by_number: dict[int, ParsedIssue],
    issue_records_by_number: dict[int, GitHubIssueRecord],
    *,
    stale_claim_timeout: timedelta,
    now: datetime,
    active_agent_run_issue_numbers: frozenset[int] = frozenset(),
) -> tuple[dict[int, int], int]:
    counts: dict[int, int] = {}
    # Track which issue numbers are already counted via durable GitHub claims.
    counted_issue_numbers: set[int] = set()
    for parsed in parsed_by_number.values():
        if not isinstance(parsed, ImplementationIssue):
            continue
        record = issue_records_by_number.get(parsed.issue.number)
        if record is None or record.state != "open":
            continue
        if parsed.parent_prd_number is None or not _has_claim_metadata(parsed):
            continue
        if _is_stale_claim(parsed, stale_claim_timeout=stale_claim_timeout, now=now):
            continue
        counts[parsed.parent_prd_number] = counts.get(parsed.parent_prd_number, 0) + 1
        counted_issue_numbers.add(parsed.issue.number)

    # Add in-memory active Agent Runs that are not already counted via GitHub claims.
    unassigned_count = 0
    for issue_number in sorted(active_agent_run_issue_numbers):
        if issue_number in counted_issue_numbers:
            continue
        parsed = parsed_by_number.get(issue_number)
        if not isinstance(parsed, ImplementationIssue):
            unassigned_count += 1
            continue
        record = issue_records_by_number.get(issue_number)
        if record is None or record.state != "open":
            unassigned_count += 1
            continue
        if parsed.parent_prd_number is None:
            unassigned_count += 1
            continue
        counts[parsed.parent_prd_number] = counts.get(parsed.parent_prd_number, 0) + 1

    return counts, unassigned_count


def _validate_dependencies(
    issue: ImplementationIssue,
    parsed_by_number: dict[int, ParsedIssue],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for blocker_number in issue.blocked_by:
        blocker = parsed_by_number.get(blocker_number)
        if blocker is None:
            diagnostics.append(
                Diagnostic(
                    code="missing-blocking-dependency",
                    kind=DiagnosticKind.INVALID_STATE,
                    message=f"Blocking dependency #{blocker_number} could not be resolved.",
                )
            )
            continue
        if not isinstance(blocker, ImplementationIssue):
            diagnostics.append(
                Diagnostic(
                    code="invalid-blocking-dependency-kind",
                    kind=DiagnosticKind.INVALID_STATE,
                    message=f"Blocking dependency #{blocker_number} is not an Implementation Issue.",
                )
            )
            continue
        if blocker.parent_prd_number != issue.parent_prd_number:
            diagnostics.append(
                Diagnostic(
                    code="cross-prd-blocking-dependency",
                    kind=DiagnosticKind.INVALID_STATE,
                    message=(
                        f"Blocking dependency #{blocker_number} belongs to PRD "
                        f"#{blocker.parent_prd_number}, not PRD #{issue.parent_prd_number}."
                    ),
                )
            )
    return tuple(diagnostics)


def _has_claim_metadata(issue: ImplementationIssue) -> bool:
    orchestration = issue.orchestration
    return any(
        (
            orchestration.agent_run_id,
            orchestration.claimed_at,
            orchestration.implementation_branch,
        )
    )


def _is_stale_claim(
    issue: ImplementationIssue,
    *,
    stale_claim_timeout: timedelta,
    now: datetime,
) -> bool:
    claimed_at = issue.orchestration.claimed_at
    if claimed_at is None:
        return False

    parsed = _parse_iso_timestamp(claimed_at)
    if parsed is None:
        return True
    return now - parsed >= stale_claim_timeout


def _parse_iso_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_open_implementation_issue(
    parsed: ParsedIssue | None,
    record: GitHubIssueRecord | None,
) -> bool:
    return isinstance(parsed, ImplementationIssue) and record is not None and record.state == "open"
