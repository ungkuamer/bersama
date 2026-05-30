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
