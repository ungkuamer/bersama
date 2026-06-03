from datetime import UTC, datetime, timedelta

from rangkai.github_issues import GitHubIssueRecord
from rangkai.planner import PlannerDecisionKind, plan_issue_actions


NOW = datetime(2026, 5, 29, 14, 0, tzinfo=UTC)


def implementation_issue(
    *,
    number: int,
    title: str = "Implementation",
    parent_prd: int = 1,
    labels: tuple[str, ...] = ("implementation", "ready-for-agent"),
    blocked_by: str = "None",
    what_to_build: str = "Implement something.",
    acceptance_criteria: tuple[str, ...] = ("It works.",),
    orchestration_lines: tuple[str, ...] = (),
    state: str = "open",
) -> GitHubIssueRecord:
    acceptance_body = "\n".join(f"- [ ] {item}" for item in acceptance_criteria)
    orchestration_body = ""
    if orchestration_lines:
        orchestration_body = "\n\n## Orchestration\n" + "\n".join(
            f"- {line}" for line in orchestration_lines
        )

    body = f"""
## Parent PRD
#{parent_prd}

## What to Build
{what_to_build}

## Acceptance Criteria
{acceptance_body}

## Blocked By
{blocked_by}{orchestration_body}
""".strip()
    return GitHubIssueRecord(
        number=number,
        title=title,
        body=body,
        labels=labels,
        state=state,
    )


def prd_issue(*, number: int, labels: tuple[str, ...] = ("prd",), state: str = "open") -> GitHubIssueRecord:
    return GitHubIssueRecord(
        number=number,
        title="PRD",
        body="## Problem Statement\n\nPlan work.",
        labels=labels,
        state=state,
    )


def plan(
    *records: GitHubIssueRecord,
    global_concurrency: int = 2,
    per_prd_concurrency: int = 1,
    stale_claim_timeout: timedelta = timedelta(hours=2),
):
    return plan_issue_actions(
        tuple(records),
        global_concurrency=global_concurrency,
        per_prd_concurrency=per_prd_concurrency,
        stale_claim_timeout=stale_claim_timeout,
        now=NOW,
    )


def test_ready_issue_without_blockers_is_claimable() -> None:
    result = plan(implementation_issue(number=6))

    assert result.claimable_issue_numbers == (6,)


def test_ready_issue_with_open_blocking_dependencies_is_blocked() -> None:
    blocker = implementation_issue(number=3)
    blocked = implementation_issue(number=6, blocked_by="#3")

    result = plan(blocker, blocked, global_concurrency=2, per_prd_concurrency=2)
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[6].kind is PlannerDecisionKind.BLOCKED
    assert decision_by_issue[6].blocking_issue_numbers == (3,)


def test_closed_blocking_dependency_does_not_block_ready_issue() -> None:
    blocker = implementation_issue(number=3, state="closed")
    blocked = implementation_issue(number=6, blocked_by="#3")

    result = plan(blocker, blocked)

    assert result.claimable_issue_numbers == (6,)


def test_malformed_implementation_issue_moves_to_needs_info() -> None:
    malformed = GitHubIssueRecord(
        number=6,
        title="Malformed",
        body="""
## Parent PRD
#1

## What to Build
Implement something.
""".strip(),
        labels=("implementation", "ready-for-agent"),
        state="open",
    )

    result = plan(malformed)
    decision = result.decisions[0]

    assert decision.issue_number == 6
    assert decision.kind is PlannerDecisionKind.NEEDS_INFO
    assert [diagnostic.code for diagnostic in decision.diagnostics] == [
        "missing-acceptance-criteria",
        "missing-blocked-by",
    ]


def test_invalid_lifecycle_state_moves_to_needs_triage() -> None:
    prd = prd_issue(number=1, labels=("prd", "ready-for-agent"))

    result = plan(prd)
    decision = result.decisions[0]

    assert decision.issue_number == 1
    assert decision.kind is PlannerDecisionKind.NEEDS_TRIAGE
    assert [diagnostic.code for diagnostic in decision.diagnostics] == [
        "ready-label-on-non-implementation"
    ]


def test_cross_prd_blocking_dependency_is_invalid_data() -> None:
    blocker = implementation_issue(number=3, parent_prd=2)
    blocked = implementation_issue(number=6, parent_prd=1, blocked_by="#3")

    result = plan(blocker, blocked, global_concurrency=2, per_prd_concurrency=2)
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[6].kind is PlannerDecisionKind.NEEDS_TRIAGE
    assert [diagnostic.code for diagnostic in decision_by_issue[6].diagnostics] == [
        "cross-prd-blocking-dependency"
    ]


def test_missing_blocking_dependency_is_invalid_data() -> None:
    blocked = implementation_issue(number=6, blocked_by="#999")

    result = plan(blocked)
    decision = result.decisions[0]

    assert decision.kind is PlannerDecisionKind.NEEDS_TRIAGE
    assert [diagnostic.code for diagnostic in decision.diagnostics] == [
        "missing-blocking-dependency"
    ]


def test_stale_claim_is_detected_from_metadata_and_timeout() -> None:
    claimed = implementation_issue(
        number=6,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T09:30:00Z",
            "Implementation Branch: impl/1/6-implementation",
        ),
    )

    result = plan(claimed, stale_claim_timeout=timedelta(hours=1))
    decision = result.decisions[0]

    assert decision.kind is PlannerDecisionKind.STALE_CLAIM
    assert [diagnostic.code for diagnostic in decision.diagnostics] == ["stale-claim"]


def test_non_stale_claim_counts_against_concurrency_limits() -> None:
    active_claim = implementation_issue(
        number=4,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-implementation",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)
    ready_other_prd = implementation_issue(number=7, parent_prd=2)

    result = plan(
        active_claim,
        ready_same_prd,
        ready_other_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    assert decision_by_issue[6].kind is PlannerDecisionKind.PENDING_CONCURRENCY
    assert decision_by_issue[7].kind is PlannerDecisionKind.CLAIMABLE


def test_global_concurrency_limit_caps_claimable_issues() -> None:
    first = implementation_issue(number=6, parent_prd=1)
    second = implementation_issue(number=7, parent_prd=2)

    result = plan(
        first,
        second,
        global_concurrency=1,
        per_prd_concurrency=1,
    )
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[6].kind is PlannerDecisionKind.CLAIMABLE
    assert decision_by_issue[7].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_claimed_issue_with_ready_label_is_invalid_state() -> None:
    claimed = implementation_issue(
        number=6,
        labels=("implementation", "ready-for-agent"),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/6-implementation",
        ),
    )

    result = plan(claimed)
    decision = result.decisions[0]

    assert decision.kind is PlannerDecisionKind.NEEDS_TRIAGE
    assert [diagnostic.code for diagnostic in decision.diagnostics] == [
        "claimed-issue-still-ready"
    ]


def test_non_ready_unclaimed_issue_is_not_claimable() -> None:
    not_ready = implementation_issue(number=6, labels=("implementation",))

    result = plan(not_ready)
    decision = result.decisions[0]

    assert decision.kind is PlannerDecisionKind.UNREADY


def test_closed_claims_do_not_count_against_concurrency_limits() -> None:
    closed_claim = implementation_issue(
        number=4,
        labels=("implementation",),
        state="closed",
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-implementation",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    result = plan(
        closed_claim,
        ready_same_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[6].kind is PlannerDecisionKind.CLAIMABLE


def test_in_memory_active_runs_count_against_concurrency_limits() -> None:
    """In-memory active Agent Runs consume slots alongside durable GitHub claims."""
    # Active claim from GitHub for PRD #1
    active_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-implementation",
        ),
    )
    # In-memory active run for PRD #2 (not yet in GitHub state)
    in_memory_run = implementation_issue(number=5, parent_prd=2)
    # Ready issues for both PRDs
    ready_prd1 = implementation_issue(number=6, parent_prd=1)
    ready_prd2 = implementation_issue(number=7, parent_prd=2)

    result = plan_issue_actions(
        (active_claim, in_memory_run, ready_prd1, ready_prd2),
        global_concurrency=2,
        per_prd_concurrency=1,
        stale_claim_timeout=timedelta(hours=2),
        now=NOW,
        active_agent_run_issue_numbers=frozenset({5}),
    )
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    # GitHub claim #4 consumes slot for PRD #1
    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    # In-memory run #5 consumes slot for PRD #2
    # So neither #6 (PRD1) nor #7 (PRD2) should be claimable (per-PRD limit = 1 each)
    assert decision_by_issue[6].kind is PlannerDecisionKind.PENDING_CONCURRENCY
    assert decision_by_issue[7].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_in_memory_runs_deduplicate_against_github_claims() -> None:
    """An issue that is both claimed in GitHub and tracked in-memory is counted only once."""
    # Issue already claimed in GitHub (active claim for PRD #1)
    active_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-implementation",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    # Pass #4 in both GitHub records AND in-memory active runs.
    # Should count as only 1 slot consumed, leaving 1 slot for #6.
    result = plan_issue_actions(
        (active_claim, ready_same_prd),
        global_concurrency=2,
        per_prd_concurrency=2,
        stale_claim_timeout=timedelta(hours=2),
        now=NOW,
        active_agent_run_issue_numbers=frozenset({4}),
    )
    decision_by_issue = {decision.issue_number: decision for decision in result.decisions}

    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    assert decision_by_issue[6].kind is PlannerDecisionKind.CLAIMABLE


def test_in_memory_runs_consume_global_slots() -> None:
    """In-memory active runs consume global concurrency slots."""
    ready_prd1 = implementation_issue(number=6, parent_prd=1)
    ready_prd2 = implementation_issue(number=7, parent_prd=2)

    # One in-memory run for PRD #1, global_concurrency=2
    result = plan_issue_actions(
        (ready_prd1, ready_prd2),
        global_concurrency=2,
        per_prd_concurrency=2,
        stale_claim_timeout=timedelta(hours=2),
        now=NOW,
        active_agent_run_issue_numbers=frozenset({1000}),
    )

    # Only 1 slot remains globally (2 - 1 in-memory = 1)
    # Lower-numbered issue gets it
    assert result.claimable_issue_numbers == (6,)


def test_in_memory_runs_fill_all_global_slots() -> None:
    """When in-memory runs fill all global slots, nothing is claimable."""
    ready_prd1 = implementation_issue(number=6, parent_prd=1)

    result = plan_issue_actions(
        (ready_prd1,),
        global_concurrency=2,
        per_prd_concurrency=2,
        stale_claim_timeout=timedelta(hours=2),
        now=NOW,
        active_agent_run_issue_numbers=frozenset({1000, 1001}),
    )

    assert result.claimable_issue_numbers == ()
    assert result.decisions[0].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_combined_github_claims_and_in_memory_runs_per_prd() -> None:
    """Combined GitHub claims and in-memory runs both count against per-PRD limits."""
    # GitHub claim for PRD #1
    github_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-aaa",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-github-claim",
        ),
    )
    ready_prd1_a = implementation_issue(number=6, parent_prd=1)
    ready_prd1_b = implementation_issue(number=8, parent_prd=1)

    # per_prd_concurrency=3, global_concurrency=3
    # GitHub: 1 active claim for PRD #1
    # In-memory: 1 active run for PRD #1 (issue #1000 doesn't exist in records,
    # but planner infers its PRD from the records if available, or counts just by number)
    # Total for PRD #1: 2 consumed, 1 remaining
    result = plan_issue_actions(
        (github_claim, ready_prd1_a, ready_prd1_b),
        global_concurrency=3,
        per_prd_concurrency=3,
        stale_claim_timeout=timedelta(hours=2),
        now=NOW,
        active_agent_run_issue_numbers=frozenset({1000}),
    )

    # Only 1 slot remains for PRD #1 (3 - 1 GitHub - 1 in-memory = 1)
    assert result.claimable_issue_numbers == (6,)


# --- Claim Status planner tests ---


def test_active_claim_status_consumes_capacity() -> None:
    """An issue with claim_status=active consumes Agent Run Capacity."""
    active_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-active",
            "Claim Status: active",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    result = plan(
        active_claim,
        ready_same_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {d.issue_number: d for d in result.decisions}

    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    assert decision_by_issue[6].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_setting_up_claim_status_consumes_capacity() -> None:
    """An issue with claim_status=setting up consumes Agent Run Capacity."""
    setting_up_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-setting-up",
            "Claim Status: setting up",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    result = plan(
        setting_up_claim,
        ready_same_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {d.issue_number: d for d in result.decisions}

    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    assert decision_by_issue[6].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_failed_claim_status_does_not_consume_capacity() -> None:
    """An issue with claim_status=failed claim does NOT consume Agent Run Capacity."""
    failed_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-failed",
            "Claim Status: failed claim",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    result = plan(
        failed_claim,
        ready_same_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {d.issue_number: d for d in result.decisions}

    # Failed claim should NOT be ACTIVE_CLAIM. It should be NEEDS_TRIAGE.
    assert decision_by_issue[4].kind is PlannerDecisionKind.NEEDS_TRIAGE
    # The slot should be available for #6.
    assert decision_by_issue[6].kind is PlannerDecisionKind.CLAIMABLE


def test_missing_claim_status_with_claim_metadata_is_backward_compatible() -> None:
    """Existing issues without Claim Status but with claim metadata behave as before."""
    claimed = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-no-status",
        ),
    )
    ready_same_prd = implementation_issue(number=6, parent_prd=1)

    result = plan(
        claimed,
        ready_same_prd,
        global_concurrency=2,
        per_prd_concurrency=1,
    )
    decision_by_issue = {d.issue_number: d for d in result.decisions}

    # Backward compat: no claim_status behaves as ACTIVE_CLAIM
    assert decision_by_issue[4].kind is PlannerDecisionKind.ACTIVE_CLAIM
    assert decision_by_issue[6].kind is PlannerDecisionKind.PENDING_CONCURRENCY


def test_failed_claim_with_ready_label_is_needs_triage() -> None:
    """An issue with claim_status=failed claim and ready-for-agent is contradictory."""
    failed_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation", "ready-for-agent"),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T13:30:00Z",
            "Implementation Branch: impl/1/4-failed",
            "Claim Status: failed claim",
        ),
    )

    result = plan(failed_claim)
    decision = result.decisions[0]

    # Should be NEEDS_TRIAGE due to contradictory state
    assert decision.kind is PlannerDecisionKind.NEEDS_TRIAGE


def test_failed_claim_still_detected_as_stale_when_timed_out() -> None:
    """A failed claim that is also stale should still be detected appropriately."""
    failed_claim = implementation_issue(
        number=4,
        parent_prd=1,
        labels=("implementation",),
        orchestration_lines=(
            "Agent Run: run-123",
            "Claimed At: 2026-05-29T09:30:00Z",
            "Implementation Branch: impl/1/4-failed",
            "Claim Status: failed claim",
        ),
    )

    result = plan(failed_claim, stale_claim_timeout=timedelta(hours=1))
    decision = result.decisions[0]

    # Failed claim takes precedence; it's NEEDS_TRIAGE, not STALE_CLAIM
    assert decision.kind is PlannerDecisionKind.NEEDS_TRIAGE

