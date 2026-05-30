from bersama.issues import (
    DiagnosticKind,
    GitHubIssue,
    ImplementationIssue,
    IssueKind,
    PrdIssue,
    parse_issue,
    upsert_section,
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


def test_parse_styled_bold_headers() -> None:
    """Headers with bold markdown styling (**text**) are normalized and matched."""
    issue = GitHubIssue(
        number=10,
        title="Styled headers with bold",
        body="""
## **Parent PRD**
#1

## **What to Build**
Implement header normalization.

## **Acceptance Criteria**
- [ ] Bold headers work.

## **Blocked By**
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Bold headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_italic_headers() -> None:
    """Headers with italic markdown styling (*text* or _text_) are normalized."""
    issue = GitHubIssue(
        number=11,
        title="Styled headers with italic",
        body="""
## *Parent PRD*
#1

## _What to Build_
Implement header normalization.

## _Acceptance Criteria_
- [ ] Italic headers work.

## *Blocked By*
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Italic headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_trailing_colon_headers() -> None:
    """Headers with trailing colons are normalized."""
    issue = GitHubIssue(
        number=12,
        title="Styled headers with trailing colons",
        body="""
## Parent PRD:
#1

## What to Build:
Implement header normalization.

## Acceptance Criteria:
- [ ] Trailing colon headers work.

## Blocked By:
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Trailing colon headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_inline_code_headers() -> None:
    """Headers with inline code markdown (`text`) are normalized."""
    issue = GitHubIssue(
        number=13,
        title="Styled headers with inline code",
        body="""
## `Parent PRD`
#1

## `What to Build`
Implement header normalization.

## `Acceptance Criteria`
- [ ] Inline code headers work.

## `Blocked By`
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Inline code headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_headers_with_extra_whitespace() -> None:
    """Headers with extra leading/trailing whitespace inside markdown are normalized."""
    issue = GitHubIssue(
        number=14,
        title="Styled headers with extra whitespace",
        body="""
##   **  Parent PRD  **   
#1

##   What to Build   
Implement header normalization.

##   Acceptance Criteria   
- [ ] Whitespace-tolerant headers work.

##   Blocked By   
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Whitespace-tolerant headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_headers_with_mixed_formatting() -> None:
    """Headers with mixed bold, trailing colon, and whitespace are normalized."""
    issue = GitHubIssue(
        number=15,
        title="Styled headers with mixed formatting",
        body="""
## **Parent PRD**:
#1

## **What to Build**:
Implement header normalization.

## **Acceptance Criteria**:
- [ ] Mixed formatting headers work.

## **Blocked By**:
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Mixed formatting headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_parse_styled_headers_with_underscore_bold() -> None:
    """Headers with __bold__ underscore syntax are normalized."""
    issue = GitHubIssue(
        number=16,
        title="Styled headers with underscore bold",
        body="""
## __Parent PRD__
#1

## __What to Build__
Implement header normalization.

## __Acceptance Criteria__
- [ ] Underscore bold headers work.

## __Blocked By__
None
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.parent_prd_number == 1
    assert parsed.what_to_build == "Implement header normalization."
    assert parsed.acceptance_criteria == ("Underscore bold headers work.",)
    assert parsed.blocked_by == ()
    assert parsed.diagnostics == ()


def test_upsert_section_normalizes_existing_styled_header() -> None:
    """upsert_section finds and replaces existing headers even when styled."""
    body = """## **What to Build**
Old content.

## Acceptance Criteria
- [ ] Something."""

    updated = upsert_section(body, "What to Build", "New content.")

    assert "## **What to Build**" not in updated
    assert "## What to Build\nNew content." in updated


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


def test_parse_orchestration_includes_integration_pr_fields() -> None:
    """Orchestration metadata parses Integration PR and Integration Status fields."""
    issue = GitHubIssue(
        number=10,
        title="Implementation with integration PR",
        body="""
## Parent PRD
#1

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-abc
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/1/10-build-it
- Integration PR: #42
- Integration Status: pending_validation
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.orchestration.integration_pr == "42"
    assert parsed.orchestration.integration_status == "pending_validation"


def test_parse_orchestration_integration_pr_without_hash_prefix() -> None:
    """Integration PR field is parsed as raw value regardless of # prefix."""
    issue = GitHubIssue(
        number=11,
        title="Implementation with PR",
        body="""
## Parent PRD
#1

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-def
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/1/11-build-it
- Integration PR: 42
- Integration Status: merged
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.orchestration.integration_pr == "42"
    assert parsed.orchestration.integration_status == "merged"


def test_parse_orchestration_without_integration_fields_returns_none() -> None:
    """When Integration PR and Integration Status are absent, they default to None."""
    issue = GitHubIssue(
        number=12,
        title="Implementation without integration",
        body="""
## Parent PRD
#1

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-ghi
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/1/12-build-it
""".strip(),
        labels=("implementation",),
    )

    parsed = parse_issue(issue)

    assert isinstance(parsed, ImplementationIssue)
    assert parsed.orchestration.integration_pr is None
    assert parsed.orchestration.integration_status is None


def test_parse_orchestration_integration_status_values() -> None:
    """Integration Status supports all defined states."""
    for status in ("pending_validation", "merged", "conflict", "failed"):
        issue = GitHubIssue(
            number=13,
            title="Test status",
            body=f"""
## Parent PRD
#1

## What to Build
Build it.

## Acceptance Criteria
- [ ] Done.

## Blocked By
None

## Orchestration
- Agent Run: run-xyz
- Claimed At: 2026-05-30T10:00:00Z
- Implementation Branch: impl/1/13-test
- Integration PR: #99
- Integration Status: {status}
""".strip(),
            labels=("implementation",),
        )

        parsed = parse_issue(issue)

        assert isinstance(parsed, ImplementationIssue)
        assert parsed.orchestration.integration_pr == "99"
        assert parsed.orchestration.integration_status == status, f"Failed for status: {status}"
