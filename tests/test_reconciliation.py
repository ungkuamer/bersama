from datetime import UTC, datetime, timedelta

from bersama.github_issues import GitHubIssueRecord
from bersama.reconciliation import ReconciliationService


class FakeIssueGateway:
    def __init__(self, *issues: GitHubIssueRecord) -> None:
        self.issues = {issue_record.number: issue_record for issue_record in issues}
        # To simulate list_issues and view_issue, let's keep a dynamic copy of the records.
        self._records = {issue.number: issue for issue in issues}
        self.added_labels = []
        self.removed_labels = []
        self.comments = []

    def list_issues(
        self,
        *,
        state: str = "open",
        label: str | None = None,
        labels: tuple[str, ...] | None = None,
        updated_since: str | None = None,
    ) -> tuple[GitHubIssueRecord, ...]:
        result = list(self._records.values())
        if labels is not None:
            label_set = set(labels)
            result = [r for r in result if set(r.labels) & label_set]
        if state != "all":
            result = [r for r in result if r.state == state]
        return tuple(result)

    def view_issue(self, number: int) -> GitHubIssueRecord:
        return self._records[number]

    def add_comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def add_labels(self, number: int, *labels: str) -> None:
        record = self._records[number]
        new_labels = tuple(sorted(set(record.labels) | set(labels)))
        self._records[number] = GitHubIssueRecord(
            number=record.number,
            title=record.title,
            body=record.body,
            labels=new_labels,
            state=record.state,
        )
        self.added_labels.append((number, labels))

    def remove_labels(self, number: int, *labels: str) -> None:
        record = self._records[number]
        new_labels = tuple(sorted(set(record.labels) - set(labels)))
        self._records[number] = GitHubIssueRecord(
            number=record.number,
            title=record.title,
            body=record.body,
            labels=new_labels,
            state=record.state,
        )
        self.removed_labels.append((number, labels))

    def update_body(self, number: int, body: str) -> None:
        record = self._records[number]
        self._records[number] = GitHubIssueRecord(
            number=record.number,
            title=record.title,
            body=body,
            labels=record.labels,
            state=record.state,
        )


def test_malformed_missing_info_moves_to_needs_info() -> None:
    # An implementation issue missing Acceptance Criteria and Blocked By
    malformed = GitHubIssueRecord(
        number=1,
        title="Implementation Task",
        body="""
## Parent PRD
#2

## What to Build
Do something.
        """.strip(),
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    gateway = FakeIssueGateway(malformed)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert (1, ("needs-info",)) in gateway.added_labels
    assert (1, ("ready-for-agent",)) in gateway.removed_labels
    assert len(gateway.comments) == 1
    assert "Missing Acceptance Criteria" in gateway.comments[0][1]


def test_malformed_invalid_state_moves_to_needs_triage() -> None:
    # An issue with both prd and implementation labels (invalid lifecycle state)
    ambiguous = GitHubIssueRecord(
        number=3,
        title="Ambiguous issue",
        body="",
        labels=("prd", "implementation"),
        state="open",
    )
    gateway = FakeIssueGateway(ambiguous)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert (3, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "Issue cannot be both a PRD Issue" in gateway.comments[0][1]


def test_no_double_label_or_comment_if_already_triaged() -> None:
    malformed = GitHubIssueRecord(
        number=1,
        title="Implementation Task",
        body="""
## Parent PRD
#2

## What to Build
Do something.
        """.strip(),
        labels=("implementation", "needs-info"),
        state="open",
    )
    gateway = FakeIssueGateway(malformed)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert len(gateway.added_labels) == 0
    assert len(gateway.comments) == 0


def test_stale_claim_moves_to_needs_triage() -> None:
    # A claimed issue that has timed out
    stale_claim = GitHubIssueRecord(
        number=4,
        title="Stale claim issue",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-123
- Claimed At: 2026-05-29T10:00:00Z
- Implementation Branch: impl/2/4-stale
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(stale_claim)
    # Set current time to 3 hours later
    service = ReconciliationService(
        issues=gateway,
        stale_claim_timeout=timedelta(hours=2),
        now_provider=lambda: "2026-05-29T13:00:00Z",
    )
    service.reconcile()

    assert (4, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "become stale" in gateway.comments[0][1]


def test_fresh_claim_remains_active() -> None:
    # A fresh claim within timeout
    fresh_claim = GitHubIssueRecord(
        number=4,
        title="Fresh claim issue",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-123
- Claimed At: 2026-05-29T12:00:00Z
- Implementation Branch: impl/2/4-fresh
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(fresh_claim)
    service = ReconciliationService(
        issues=gateway,
        stale_claim_timeout=timedelta(hours=2),
        now_provider=lambda: "2026-05-29T13:00:00Z",
    )
    service.reconcile()

    assert len(gateway.added_labels) == 0
    assert len(gateway.comments) == 0


def test_prd_receives_ready_for_human_when_all_children_closed() -> None:
    prd = GitHubIssueRecord(
        number=2,
        title="Parent PRD",
        body="## Problem Statement\n\nPlan features.",
        labels=("prd",),
        state="open",
    )
    child1 = GitHubIssueRecord(
        number=5,
        title="Child 1",
        body="""
## Parent PRD
#2

## What to Build
Do 1.

## Acceptance Criteria
- [ ] Done 1.

## Blocked By
None
        """.strip(),
        labels=("implementation",),
        state="closed",
    )
    child2 = GitHubIssueRecord(
        number=6,
        title="Child 2",
        body="""
## Parent PRD
#2

## What to Build
Do 2.

## Acceptance Criteria
- [ ] Done 2.

## Blocked By
None
        """.strip(),
        labels=("implementation",),
        state="closed",
    )

    gateway = FakeIssueGateway(prd, child1, child2)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert (2, ("ready-for-human",)) in gateway.added_labels
    assert gateway.view_issue(2).state == "open"  # Must not be closed automatically


def test_prd_remains_unchanged_when_some_children_still_open() -> None:
    prd = GitHubIssueRecord(
        number=2,
        title="Parent PRD",
        body="## Problem Statement\n\nPlan features.",
        labels=("prd",),
        state="open",
    )
    child1 = GitHubIssueRecord(
        number=5,
        title="Child 1",
        body="""
## Parent PRD
#2

## What to Build
Do 1.

## Acceptance Criteria
- [ ] Done 1.

## Blocked By
None
        """.strip(),
        labels=("implementation",),
        state="closed",
    )
    child2 = GitHubIssueRecord(
        number=6,
        title="Child 2",
        body="""
## Parent PRD
#2

## What to Build
Do 2.

## Acceptance Criteria
- [ ] Done 2.

## Blocked By
None
        """.strip(),
        labels=("implementation",),
        state="open",
    )

    gateway = FakeIssueGateway(prd, child1, child2)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert len(gateway.added_labels) == 0


def test_resolved_issue_self_heals() -> None:
    # An implementation issue that has "needs-info" but no longer has diagnostics (resolved)
    resolved = GitHubIssueRecord(
        number=10,
        title="Implementation Task",
        body="""
## Parent PRD
#2

## What to Build
Do something.

## Acceptance Criteria
- [ ] Done 1.

## Blocked By
None
        """.strip(),
        labels=("implementation", "needs-info"),
        state="open",
    )
    gateway = FakeIssueGateway(resolved)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    # Verify needs-info is removed and ready-for-agent is restored
    assert (10, ("needs-info",)) in gateway.removed_labels
    assert (10, ("ready-for-agent",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "has been resolved and is now ready for agent execution" in gateway.comments[0][1]


# --- Claim Status reconciliation tests ---


def test_unrecognised_claim_status_detected_by_reconciliation() -> None:
    """Reconciliation detects an unrecognised Claim Status value and moves to needs-triage."""
    issue = GitHubIssueRecord(
        number=20,
        title="Bad claim status",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-abc
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/2/20-build-it
- Claim Status: bogus-value
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    # Unrecognised claim status should be caught as an INVALID_STATE diagnostic
    # which moves the issue to needs-triage.
    assert (20, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) > 0
    comment_text = gateway.comments[0][1]
    assert "unrecognised-claim-status" in comment_text or "Claim Status" in comment_text


def test_failed_claim_status_moves_issue_to_needs_triage_for_human_review() -> None:
    """A failed claim setup remains reviewable until a human resolves it."""
    issue = GitHubIssueRecord(
        number=21,
        title="Failed claim issue",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-def
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/2/21-build-it
- Claim Status: failed claim
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    # Use a now_provider within the 2h window so the claim is not stale.
    service = ReconciliationService(
        issues=gateway,
        now_provider=lambda: "2026-05-30T11:00:00Z",
    )
    service.reconcile()

    assert (21, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "Failed Claim Setup" in gateway.comments[0][1]
    assert "Claim Status: failed claim" in gateway.comments[0][1]


def test_active_claim_status_preserves_normal_behaviour() -> None:
    """An active claim with claim_status=active behaves like any other active claim."""
    issue = GitHubIssueRecord(
        number=22,
        title="Active claim with status",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-ghi
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/2/22-build-it
- Claim Status: active
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(
        issues=gateway,
        now_provider=lambda: "2026-05-30T11:00:00Z",
    )
    service.reconcile()

    # No malformed diagnostics, and claim is not stale (within 2h timeout).
    assert len(gateway.added_labels) == 0
    assert len(gateway.comments) == 0


def test_failed_claim_with_ready_label_cleared_by_reconciliation() -> None:
    """When reconciliation encounters a failed claim with ready-for-agent, the ready
    label should be removed because parsing produces an unrecognised-claim-status
    diagnostic (if unrecognised) OR the failed claim is treated as unhealthy.

    For a *recognised* failed claim with ready-for-agent, reconciliation should
    still detect the contradiction and move to needs-triage.
    """
    issue = GitHubIssueRecord(
        number=23,
        title="Failed claim with ready",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-jkl
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/2/23-build-it
- Claim Status: failed claim
        """.strip(),
        labels=("implementation", "ready-for-agent"),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    # The ready-for-agent label is contradictory with a failed claim.
    # Reconciliation should remove the ready labels and add needs-triage.
    assert (23, ("ready-for-agent",)) in gateway.removed_labels
    assert len(gateway.comments) > 0


def test_malformed_claim_status_with_other_diagnostics_combined() -> None:
    """When an issue has both an unrecognised claim status and other missing
    sections, reconciliation reports all diagnostics together."""
    issue = GitHubIssueRecord(
        number=24,
        title="Multiple problems",
        body="""
## Parent PRD
#2

## Orchestration
- Claim Status: totally-wrong
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(issues=gateway)
    service.reconcile()

    assert (24, ("needs-triage",)) in gateway.added_labels
    comment = gateway.comments[0][1]
    assert "Unrecognised Claim Status" in comment
    assert "Missing What to Build" in comment or "missing-what-to-build" in comment


def test_stale_provisional_claim_setup_moves_to_needs_triage_with_diagnostics() -> None:
    issue = GitHubIssueRecord(
        number=25,
        title="Interrupted claim setup",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-stale
- Claimed At: 2026-05-30T08:00:00Z
- Claim Status: setting up
- Implementation Branch: impl/2/25-build-it
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(
        issues=gateway,
        stale_claim_timeout=timedelta(hours=2),
        now_provider=lambda: "2026-05-30T11:00:00Z",
    )

    service.reconcile()

    assert (25, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "Interrupted Claim Setup" in gateway.comments[0][1]
    assert "Claim Status: setting up" in gateway.comments[0][1]


def test_legacy_claim_metadata_without_claim_status_stays_backward_compatible() -> None:
    issue = GitHubIssueRecord(
        number=26,
        title="Legacy claimed issue",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-legacy
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/2/26-build-it
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(
        issues=gateway,
        stale_claim_timeout=timedelta(hours=2),
        now_provider=lambda: "2026-05-30T11:00:00Z",
    )

    service.reconcile()

    assert len(gateway.added_labels) == 0
    assert len(gateway.comments) == 0


def test_stale_legacy_claim_metadata_uses_existing_stale_claim_path() -> None:
    issue = GitHubIssueRecord(
        number=27,
        title="Legacy stale claim",
        body="""
## Parent PRD
#2

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-legacy-stale
- Claimed At: 2026-05-30T08:00:00Z
- Implementation Branch: impl/2/27-build-it
        """.strip(),
        labels=("implementation",),
        state="open",
    )
    gateway = FakeIssueGateway(issue)
    service = ReconciliationService(
        issues=gateway,
        stale_claim_timeout=timedelta(hours=2),
        now_provider=lambda: "2026-05-30T11:00:00Z",
    )

    service.reconcile()

    assert (27, ("needs-triage",)) in gateway.added_labels
    assert len(gateway.comments) == 1
    assert "has become stale" in gateway.comments[0][1]
    assert "Claim Status" not in gateway.comments[0][1]
