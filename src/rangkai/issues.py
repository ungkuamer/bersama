from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re


ISSUE_REFERENCE_RE = re.compile(r"#(\d+)")
SECTION_RE = re.compile(r"^## (?P<name>.+)$", re.MULTILINE)
CHECKLIST_ITEM_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(?P<text>.+?)\s*$", re.MULTILINE)
ORCHESTRATION_ITEM_RE = re.compile(r"^\s*-\s*(?P<key>[^:]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)


class ClaimStatus(Enum):
    SETTING_UP = "setting up"
    ACTIVE = "active"
    FAILED = "failed claim"


def parse_claim_status(value: str | None) -> ClaimStatus | None:
    """Parse a raw claim status string into a ClaimStatus enum value.

    Returns None when the value is None, empty, or unrecognised.
    Callers must decide whether unrecognised values should be treated as
    diagnostics.
    """
    if value is None:
        return None
    normalised = value.strip().lower()
    if not normalised:
        return None
    if normalised == "setting up":
        return ClaimStatus.SETTING_UP
    if normalised == "active":
        return ClaimStatus.ACTIVE
    if normalised in ("failed claim", "failed"):
        return ClaimStatus.FAILED
    return None


def _claim_status_is_recognised(value: str | None) -> bool:
    """Return True when the claim-status value is absent or recognised."""
    if value is None:
        return True
    normalised = value.strip().lower()
    if not normalised:
        return True
    return parse_claim_status(value) is not None


class IssueKind(Enum):
    PRD = "prd"
    IMPLEMENTATION = "implementation"
    UNKNOWN = "unknown"


class DiagnosticKind(Enum):
    MISSING_INFO = "missing-info"
    INVALID_STATE = "invalid-state"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    kind: DiagnosticKind
    message: str


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class OrchestrationMetadata:
    agent_run_id: str | None = None
    claimed_at: str | None = None
    claim_status: str | None = None
    prd_branch: str | None = None
    implementation_branch: str | None = None
    integration_pr: str | None = None
    integration_status: str | None = None


@dataclass(frozen=True)
class ParsedIssue:
    issue: GitHubIssue
    kind: IssueKind
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class ImplementationIssue(ParsedIssue):
    parent_prd_number: int | None = None
    what_to_build: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    blocked_by: tuple[int, ...] = ()
    orchestration: OrchestrationMetadata = field(default_factory=OrchestrationMetadata)


@dataclass(frozen=True)
class PrdIssue(ParsedIssue):
    orchestration: OrchestrationMetadata = field(default_factory=OrchestrationMetadata)


def parse_issue(issue: GitHubIssue) -> ParsedIssue:
    labels = set(issue.labels)
    if "prd" in labels and "implementation" in labels:
        return ParsedIssue(
            issue=issue,
            kind=IssueKind.UNKNOWN,
            diagnostics=(
                Diagnostic(
                    code="ambiguous-issue-kind",
                    kind=DiagnosticKind.INVALID_STATE,
                    message="Issue cannot be both a PRD Issue and an Implementation Issue.",
                ),
            ),
        )

    if "implementation" in labels:
        return _parse_implementation_issue(issue)

    if "prd" in labels:
        sections = _parse_sections(issue.body)
        return PrdIssue(
            issue=issue,
            kind=IssueKind.PRD,
            orchestration=_parse_orchestration(sections.get("Orchestration")),
        )

    return ParsedIssue(issue=issue, kind=IssueKind.UNKNOWN)


def _parse_implementation_issue(issue: GitHubIssue) -> ImplementationIssue:
    sections = _parse_sections(issue.body)
    diagnostics: list[Diagnostic] = []

    def get_section(names: list[str]) -> str | None:
        for name in names:
            normalized = _normalize_header(name)
            for key, val in sections.items():
                if key.lower() == normalized.lower():
                    return val
        return None

    parent_prd_body = get_section(["Parent PRD", "Parent"])
    if parent_prd_body is None:
        parent_prd_number = None
        diagnostics.append(_missing("missing-parent-prd", "Missing Parent PRD section."))
    else:
        parent_refs = _extract_issue_references(parent_prd_body)
        if len(parent_refs) != 1:
            parent_prd_number = None
            diagnostics.append(
                Diagnostic(
                    code="invalid-parent-prd",
                    kind=DiagnosticKind.MISSING_INFO,
                    message="Parent PRD must contain exactly one issue reference.",
                )
            )
        else:
            parent_prd_number = parent_refs[0]

    what_to_build_body = get_section(["What to Build", "What to build"])
    if what_to_build_body is None:
        what_to_build = ""
        diagnostics.append(_missing("missing-what-to-build", "Missing What to Build section."))
    else:
        what_to_build = what_to_build_body.strip()

    acceptance_criteria_body = get_section(["Acceptance Criteria", "Acceptance criteria"])
    if acceptance_criteria_body is None:
        acceptance_criteria = ()
        diagnostics.append(
            _missing("missing-acceptance-criteria", "Missing Acceptance Criteria section.")
        )
    else:
        acceptance_criteria = tuple(
            match.group("text").strip()
            for match in CHECKLIST_ITEM_RE.finditer(acceptance_criteria_body)
        )

    blocked_by_body = get_section(["Blocked By", "Blocked by"])
    if blocked_by_body is None:
        blocked_by = ()
        diagnostics.append(_missing("missing-blocked-by", "Missing Blocked By section."))
    else:
        blocked_by, blocked_by_diagnostic = _parse_blocked_by(blocked_by_body)
        if blocked_by_diagnostic is not None:
            diagnostics.append(blocked_by_diagnostic)

    orchestration = _parse_orchestration(get_section(["Orchestration"]))

    # Diagnose unrecognised Claim Status values.
    if orchestration.claim_status is not None and not _claim_status_is_recognised(
        orchestration.claim_status
    ):
        diagnostics.append(
            Diagnostic(
                code="unrecognised-claim-status",
                kind=DiagnosticKind.INVALID_STATE,
                message=f"Unrecognised Claim Status value: '{orchestration.claim_status}'.",
            )
        )

    return ImplementationIssue(
        issue=issue,
        kind=IssueKind.IMPLEMENTATION,
        parent_prd_number=parent_prd_number,
        what_to_build=what_to_build,
        acceptance_criteria=acceptance_criteria,
        blocked_by=blocked_by,
        orchestration=orchestration,
        diagnostics=tuple(diagnostics),
    )


def _normalize_header(name: str) -> str:
    """Normalize a section header by stripping markdown formatting, trailing colons, and whitespace."""
    name = name.strip()
    for ch in ("*", "_", "`"):
        name = name.replace(ch, "")
    name = name.rstrip(":")
    return name.strip()


def _parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[_normalize_header(match.group("name"))] = body[start:end].strip()
    return sections


def _extract_issue_references(text: str) -> list[int]:
    return [int(match.group(1)) for match in ISSUE_REFERENCE_RE.finditer(text)]


def _parse_blocked_by(body: str) -> tuple[tuple[int, ...], Diagnostic | None]:
    stripped = body.strip()
    if not stripped or stripped.lower().startswith("none"):
        return (), None

    refs = tuple(_extract_issue_references(body))
    if refs:
        return refs, None

    return (), Diagnostic(
        code="invalid-blocked-by",
        kind=DiagnosticKind.MISSING_INFO,
        message="Blocked By must be empty, say none, or contain issue references.",
    )


def _strip_hash_prefix(value: str | None) -> str | None:
    """Strip optional leading '#' from a PR number value."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped.startswith("#"):
        return stripped[1:].strip()
    return stripped


def _parse_orchestration(body: str | None) -> OrchestrationMetadata:
    if not body:
        return OrchestrationMetadata()

    values: dict[str, str] = {}
    for match in ORCHESTRATION_ITEM_RE.finditer(body):
        values[match.group("key").strip().lower()] = match.group("value").strip()

    return OrchestrationMetadata(
        agent_run_id=values.get("agent run"),
        claimed_at=values.get("claimed at"),
        claim_status=values.get("claim status"),
        prd_branch=values.get("prd branch"),
        implementation_branch=values.get("implementation branch"),
        integration_pr=_strip_hash_prefix(values.get("integration pr")),
        integration_status=values.get("integration status"),
    )


def upsert_section(body: str, section_name: str, section_body: str) -> str:
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return f"{body.rstrip()}\n\n## {section_name}\n{section_body.strip()}".strip()

    for index, match in enumerate(matches):
        if _normalize_header(match.group("name")) != _normalize_header(section_name):
            continue

        section_start = match.start()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        replacement = f"## {section_name}\n{section_body.strip()}"
        prefix = body[:section_start].rstrip()
        suffix = body[section_end:].lstrip()
        if prefix and suffix:
            return f"{prefix}\n\n{replacement}\n\n{suffix}".strip()
        if prefix:
            return f"{prefix}\n\n{replacement}".strip()
        if suffix:
            return f"{replacement}\n\n{suffix}".strip()
        return replacement

    return f"{body.rstrip()}\n\n## {section_name}\n{section_body.strip()}".strip()


def _missing(code: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, kind=DiagnosticKind.MISSING_INFO, message=message)
