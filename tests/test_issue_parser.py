from bersama.issues import (
    DiagnosticKind,
    GitHubIssue,
    ImplementationIssue,
    IssueKind,
    PrdIssue,
    parse_issue,
)


def test_parse_prd_issue_from_prd_label() -> None:
    issue = GitHubIssue(
        number=1,
        title="Build LangGraph agent orchestration system",
        body="## Problem Statement\n\nCoordinate agent work through GitHub Issues.",
        labels=("prd",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, PrdIssue)
    assert parsed.kind is IssueKind.PRD
    assert parsed.diagnostics == ()


def test_parse_prd_orchestration_metadata_when_present() -> None:
    issue = GitHubIssue(
        number=1,
        title="Build LangGraph agent orchestration system",
        body="""
## Problem Statement

Coordinate agent work through GitHub Issues.

## Orchestration
- PRD Branch: prd/1-build-langgraph-agent-orchestration-system
""".strip(),
        labels=("prd",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, PrdIssue)
    assert (
        parsed.orchestration.prd_branch
        == "prd/1-build-langgraph-agent-orchestration-system"
    )


def test_parse_valid_implementation_issue() -> None:
    issue = GitHubIssue(
        number=3,
        title="Parse and validate PRD Issues and Implementation Issues",
        body="""
## Parent PRD
#1

## What to Build
Implement the Issue Model and Parser for PRD Issues and Implementation Issues.

## Acceptance Criteria
- [ ] PRD Issues are recognized from the prd label.
- [ ] Implementation Issues are recognized from the implementation label.

## Blocked By
None - can start immediately
""".strip(),
        labels=("implementation", "ready-for-agent"),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.kind is IssueKind.IMPLEMENTATION
    assert parsed.parent_prd_number == 1
    assert (
        parsed.what_to_build
        == "Implement the Issue Model and Parser for PRD Issues and Implementation Issues."
    )
    assert parsed.acceptance_criteria == (
        "PRD Issues are recognized from the prd label.",
        "Implementation Issues are recognized from the implementation label.",
    )
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_missing_required_sections_reports_missing_info() -> None:
    issue = GitHubIssue(
        number=4,
        title="Incomplete implementation issue",
        body="""
## Parent PRD
#1

## What to Build
Implement something.
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.kind is IssueKind.IMPLEMENTATION
    assert [diagnostic.code for diagnostic in parsed.diagnostics] == [
        "missing-acceptance-criteria",
        "missing-blocked-by",
    ]
    assert all(
        diagnostic.kind is DiagnosticKind.MISSING_INFO
        for diagnostic in parsed.diagnostics
    )


def test_parse_parent_prd_requires_exactly_one_issue_reference() -> None:
    issue = GitHubIssue(
        number=5,
        title="Malformed parent prd",
        body="""
## Parent PRD
#1 and #2

## What to Build
Implement something.

## Acceptance Criteria
- [ ] It works.

## Blocked By
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number is None
    assert [diagnostic.code for diagnostic in parsed.diagnostics] == [
        "invalid-parent-prd"
    ]
    assert parsed.diagnostics[0].kind is DiagnosticKind.MISSING_INFO


def test_parse_blocked_by_allows_multiple_issue_references() -> None:
    issue = GitHubIssue(
        number=6,
        title="Blocked implementation issue",
        body="""
## Parent PRD
#1

## What to Build
Implement something.

## Acceptance Criteria
- [ ] It works.

## Blocked By
- #2
- depends on #7
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.blocked_by == (2, 7)
    assert parsed.diagnostics == ()


def test_parse_blocked_by_rejects_non_reference_content() -> None:
    issue = GitHubIssue(
        number=7,
        title="Malformed blockers",
        body="""
## Parent PRD
#1

## What to Build
Implement something.

## Acceptance Criteria
- [ ] It works.

## Blocked By
waiting on design review
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.blocked_by == ()
    assert [diagnostic.code for diagnostic in parsed.diagnostics] == [
        "invalid-blocked-by"
    ]
    assert parsed.diagnostics[0].kind is DiagnosticKind.MISSING_INFO


def test_parse_labels_distinguishes_invalid_lifecycle_state() -> None:
    issue = GitHubIssue(
        number=8,
        title="Ambiguous issue labels",
        body="",
        labels=("prd", "implementation"),
    )

    parsed = parse_issue(issue)

    assert parsed.kind is IssueKind.UNKNOWN
    assert [diagnostic.code for diagnostic in parsed.diagnostics] == [
        "ambiguous-issue-kind"
    ]
    assert parsed.diagnostics[0].kind is DiagnosticKind.INVALID_STATE


def test_parse_orchestration_metadata_when_present() -> None:
    issue = GitHubIssue(
        number=9,
        title="Prepared implementation issue",
        body="""
## Parent PRD
#1

## What to Build
Implement something.

## Acceptance Criteria
- [ ] It works.

## Blocked By
None

## Orchestration
- Agent Run: run-123
- Claimed At: 2026-05-29T09:30:00Z
- Implementation Branch: impl/1/9-implement-something
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.orchestration.agent_run_id == "run-123"
    assert parsed.orchestration.claimed_at == "2026-05-29T09:30:00Z"
    assert (
        parsed.orchestration.implementation_branch
        == "impl/1/9-implement-something"
    )
