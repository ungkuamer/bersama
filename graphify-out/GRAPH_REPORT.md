# Graph Report - bersama  (2026-05-30)

## Corpus Check
- 96 files · ~75,296 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1276 nodes · 3094 edges · 95 communities (79 shown, 16 thin omitted)
- Extraction: 61% EXTRACTED · 39% INFERRED · 0% AMBIGUOUS · INFERRED: 1206 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e161cdbe`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]

## God Nodes (most connected - your core abstractions)
1. `GitHubIssue` - 100 edges
2. `GitHubIssueRecord` - 97 edges
3. `GitHubIssueGateway` - 78 edges
4. `PrdIssue` - 74 edges
5. `RepoConfig` - 70 edges
6. `Orchestrator` - 67 edges
7. `IntegrationWorkspaceGateway` - 63 edges
8. `ImplementationIssue` - 63 edges
9. `AppConfig` - 60 edges
10. `ClaimWorkspaceGateway` - 58 edges

## Surprising Connections (you probably didn't know these)
- `str` --uses--> `ConfigError`  [INFERRED]
  tests/test_config.py → src/bersama/config.py
- `FakeGitRunner` --uses--> `UpdateError`  [INFERRED]
  tests/test_integration.py → src/bersama/integration.py
- `FakeIssueGateway` --uses--> `UpdateError`  [INFERRED]
  tests/test_integration.py → src/bersama/integration.py
- `int` --uses--> `UpdateError`  [INFERRED]
  tests/test_integration.py → src/bersama/integration.py
- `Path` --uses--> `UpdateError`  [INFERRED]
  tests/test_integration.py → src/bersama/integration.py

## Communities (95 total, 16 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (90): ClaimError, GitRunner, Raised when claim setup fails., extract_last_agent_message(), IssueGateway, GitHubIssueRecord, GitRunner, IntegrationError (+82 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (83): Any, ArgumentParser, BackgroundTaskScheduler, BaseModel, ClaimWorkspaceGateway, ImplementationClaimService, _claim_issue_command(), _dashboard_command() (+75 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (59): RepoConfig, Orchestrator, Start the serialized integration worker thread if not already running., Continuously drain the integration queue, one issue at a time.         The lock, Wait for all pending integrations to complete. Called before shutdown., Continuous drain scheduling for dependency waves.          Reconciliation runs a, MagicMock, FakeIssueGateway (+51 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (55): ClaimResult, HarnessConfig, create_dashboard_app(), ExecutionResult, IntegrationResult, PrdPreparationResult, ClaimResult, ExecutionResult (+47 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (49): bool, int, str, BM25, detect_domain(), _load_csv(), BM25 ranking algorithm for text search, Lowercase, split, remove punctuation, filter short words (+41 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (40): dependencies, class-variance-authority, clsx, @fontsource-variable/geist, lucide-react, radix-ui, react, react-dom (+32 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (28): ImplementationClaimResponse, ImplementationClaimState, ImplementationIntegrationResponse, ImplementationIntegrationState, ImplementationStartResponse, ImplementationStartState, Issue, LogTail (+20 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (26): FakeGitRunner, bool, str, Tests for the Repository Operation Lock (ADR 0004).  The Repository Operation Lo, A generic fake git runner used across gateway lock tests., When ClaimWorkspaceGateway, GitWorkspaceGateway, and IntegrationWorkspaceGateway, The Orchestrator must create a single Repository Operation Lock     and pass it, The HarnessExecutionService must NOT receive or hold the Repository     Operatio (+18 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (30): For --cluster-only, For git commit hook, For /graphify add, For /graphify explain, For /graphify path, For /graphify query, For native CLAUDE.md integration, For --update (incremental re-extraction) (+22 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (30): implementation_issue(), plan(), prd_issue(), GitHubIssueRecord, int, str, timedelta, In-memory active Agent Runs consume slots alongside durable GitHub claims. (+22 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (22): compilerOptions, allowImportingTsExtensions, baseUrl, erasableSyntaxOnly, ignoreDeprecations, jsx, lib, module (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 12 - "Community 12"
Cohesion: 0.21
Nodes (12): FakeGitRunner, FakeIssueGateway, get_mock_issues(), int, Path, str, setup_real_test_git_repo(), test_integrate_issue_merge_conflict() (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.26
Nodes (12): FakeIssueGateway, GitHubIssueRecord, int, str, test_fresh_claim_remains_active(), test_malformed_invalid_state_moves_to_needs_triage(), test_malformed_missing_info_moves_to_needs_info(), test_no_double_label_or_comment_if_already_triaged() (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.20
Nodes (6): CommandRunner, run_subprocess(), int, object, Path, str

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (14): cn(), Badge(), badgeVariants, Button(), buttonVariants, Card(), CardAction(), CardContent() (+6 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (18): CLI, Component Docs, Examples, and Usage, Component Selection, Component Structure → [composition.md](./rules/composition.md), Critical Rules, Current Project Context, Detailed References, Forms & Inputs → [forms.md](./rules/forms.md) (+10 more)

### Community 17 - "Community 17"
Cohesion: 0.22
Nodes (9): build_implementation_branch_name(), run_git(), upsert_claim_metadata(), _utc_now(), bool, int, str, test_build_implementation_branch_name_uses_canonical_format() (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, moduleResolution, noEmit (+9 more)

### Community 19 - "Community 19"
Cohesion: 0.11
Nodes (17): `add` — Add components, `apply` — Apply a preset to an existing project, `build` — Build a custom registry, Commands, Contents, `diff` — Check for updates, `docs` — Get component documentation URLs, Dry-Run Mode (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.20
Nodes (9): build_prd_branch_name(), GitRunner, run_git(), upsert_prd_branch_metadata(), bool, int, str, test_build_prd_branch_name_slugifies_title() (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.38
Nodes (16): build_parser(), main(), Path, test_claim_issue_command_reports_branch_and_worktree(), test_claim_issue_command_reports_failures_to_stderr(), test_dashboard_command_starts_server(), test_execute_run_command_failure(), test_execute_run_command_success() (+8 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (14): 1. Built-in variants, 2. Tailwind classes via `className`, 3. Add a new variant, 4. Wrapper components, Adding Custom Colors, Border Radius, Changing the Theme, Checking for Updates (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.14
Nodes (13): Avatar always needs AvatarFallback, Button has no isPending or isLoading prop, Callouts use Alert, Card structure, Choosing between overlay components, Component Composition, Contents, Dialog, Sheet, and Drawer always need a Title (+5 more)

### Community 24 - "Community 24"
Cohesion: 0.29
Nodes (13): blend(), derive_row(), derive_ui_reasoning(), h2r(), is_dark(), lum(), on_color(), r2h() (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.15
Nodes (12): Configure, Install, Issue Requirements, Local Installation, Manual Operations, Prerequisites, rangkai, Read-Only API Endpoints (+4 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (12): Built-in variants first, className for layout only, Contents, No manual dark: color overrides, No manual z-index on overlay components, No raw color values for status/state indicators, No space-x-* / space-y-*, Prefer size-* over w-* h-* when equal (+4 more)

### Community 27 - "Community 27"
Cohesion: 0.17
Nodes (11): Diagnose, Iterate on the loop itself, Non-deterministic bugs, Phase 1 — Build a feedback loop, Phase 2 — Reproduce, Phase 3 — Hypothesise, Phase 4 — Instrument, Phase 5 — Fix + regression test (+3 more)

### Community 28 - "Community 28"
Cohesion: 0.17
Nodes (11): Configuring Registries, Setup, `shadcn:get_add_command_for_items`, `shadcn:get_audit_checklist`, `shadcn:get_item_examples_from_registries`, `shadcn:get_project_registries`, `shadcn:list_items_in_registries`, shadcn MCP Server (+3 more)

### Community 29 - "Community 29"
Cohesion: 0.29
Nodes (9): FakeRunner, str, test_add_and_remove_labels_edit_issue_lifecycle_state(), test_add_comment_posts_diagnostic_message(), test_close_issue_does_not_add_success_comment(), test_list_issues_can_filter_by_label(), test_list_issues_returns_open_and_closed_issue_records(), test_update_body_records_orchestration_metadata() (+1 more)

### Community 30 - "Community 30"
Cohesion: 0.17
Nodes (11): 1. Gather context, 2. Explore the codebase (optional), 3. Draft vertical slices, 4. Quiz the user, 5. Publish the issues to the issue tracker, Acceptance criteria, Blocked by, Parent (+3 more)

### Community 31 - "Community 31"
Cohesion: 0.18
Nodes (11): 10. Charts & Data (LOW), 1. Accessibility (CRITICAL), 2. Touch & Interaction (CRITICAL), 3. Performance (HIGH), 4. Style Selection (HIGH), 5. Layout & Responsive (HIGH), 6. Typography & Color (MEDIUM), 7. Animation (MEDIUM) (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.20
Nodes (9): Challenge against the glossary, Cross-reference with code, Discuss concrete scenarios, Domain awareness, During the session, File structure, Offer ADRs sparingly, Sharpen fuzzy language (+1 more)

### Community 33 - "Community 33"
Cohesion: 0.20
Nodes (9): Accordion, Base vs Radix, Button / trigger as non-button element (base only), Composition: asChild (radix) vs render (base), Contents, Select, Select — multiple selection and object values (base only), Slider (+1 more)

### Community 34 - "Community 34"
Cohesion: 0.20
Nodes (9): 1. Planning, 2. Tracer Bullet, 3. Incremental Loop, 4. Refactor, Anti-Pattern: Horizontal Slices, Checklist Per Cycle, Philosophy, Test-Driven Development (+1 more)

### Community 35 - "Community 35"
Cohesion: 0.22
Nodes (8): Further Notes, Implementation Decisions, Out of Scope, Problem Statement, Process, Solution, Testing Decisions, User Stories

### Community 36 - "Community 36"
Cohesion: 0.22
Nodes (8): Buttons inside inputs use InputGroup + InputGroupAddon, Contents, Field validation and disabled states, FieldSet + FieldLegend for grouping related fields, Forms & Inputs, Forms use FieldGroup + Field, InputGroup requires InputGroupInput/InputGroupTextarea, Option sets (2–7 choices) use ToggleGroup

### Community 37 - "Community 37"
Cohesion: 0.50
Nodes (8): Path, str, test_harness_command_template_is_loaded(), test_loads_valid_config(), test_missing_required_repo_field_raises_clear_error(), test_repo_concurrency_defaults_are_applied(), test_unknown_harness_reference_raises_error(), write_config()

### Community 38 - "Community 38"
Cohesion: 0.22
Nodes (8): Available Domains, Available Stacks, How to Use, Output Formats, Prerequisites, Rule Categories by Priority, Search Reference, UI/UX Pro Max - Design Intelligence

### Community 39 - "Community 39"
Cohesion: 0.22
Nodes (8): Description Requirements, Process, Review Checklist, SKILL.md Template, Skill Structure, When to Add Scripts, When to Split Files, Writing Skills

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (7): 1. Explore, 2. Present findings and ask, 3. Confirm and edit, 4. Write, 5. Done, Process, Setup Matt Pocock's Skills

### Community 41 - "Community 41"
Cohesion: 0.29
Nodes (6): ADR Format, Numbering, Optional sections, Template, What qualifies, When to offer an ADR

### Community 42 - "Community 42"
Cohesion: 0.33
Nodes (5): Before exploring, read these, Domain Docs, File structure, Flag ADR conflicts, Use the glossary's vocabulary

### Community 43 - "Community 43"
Cohesion: 0.33
Nodes (5): implementation_branch, issue_number, prd_branch, started_at, status

### Community 44 - "Community 44"
Cohesion: 0.33
Nodes (5): Before exploring, read these, Domain Docs, File structure, Flag ADR conflicts, Use the glossary's vocabulary

### Community 45 - "Community 45"
Cohesion: 0.33
Nodes (6): How to Use This Skill, Step 1: Analyze User Requirements, Step 2: Generate Design System (REQUIRED), Step 2b: Persist Design System (Master + Overrides Pattern), Step 3: Supplement with Detailed Searches (as needed), Step 4: Stack Guidelines (React Native)

### Community 46 - "Community 46"
Cohesion: 0.33
Nodes (6): Accessibility, Interaction, Layout, Light/Dark Mode, Pre-Delivery Checklist, Visual Quality

### Community 47 - "Community 47"
Cohesion: 0.40
Nodes (4): Conventions, Issue tracker: GitHub, When a skill says "fetch the relevant ticket", When a skill says "publish to the issue tracker"

### Community 48 - "Community 48"
Cohesion: 0.40
Nodes (4): Conventions, Issue tracker: Local Markdown, When a skill says "fetch the relevant ticket", When a skill says "publish to the issue tracker"

### Community 49 - "Community 49"
Cohesion: 0.40
Nodes (4): Agent skills, Domain docs, Issue tracker, Triage labels

### Community 50 - "Community 50"
Cohesion: 0.40
Nodes (4): Auto-Clarity Exception, Examples, Persistence, Rules

### Community 51 - "Community 51"
Cohesion: 0.40
Nodes (4): CONTEXT.md Format, Rules, Single vs multi-context repos, Structure

### Community 52 - "Community 52"
Cohesion: 0.40
Nodes (4): Icons, Icons in Button use data-icon attribute, No sizing classes on icons inside components, Pass icons as component objects, not string keys

### Community 53 - "Community 53"
Cohesion: 0.40
Nodes (4): Conventions, Issue tracker: GitHub, When a skill says "fetch the relevant ticket", When a skill says "publish to the issue tracker"

### Community 54 - "Community 54"
Cohesion: 0.40
Nodes (4): Conventions, Issue tracker: GitLab, When a skill says "fetch the relevant ticket", When a skill says "publish to the issue tracker"

### Community 55 - "Community 55"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, caveman

### Community 56 - "Community 56"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, grill-with-docs

### Community 57 - "Community 57"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, diagnose

### Community 58 - "Community 58"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, grill-me

### Community 59 - "Community 59"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, handoff

### Community 60 - "Community 60"
Cohesion: 0.40
Nodes (5): computedHash, skillPath, source, sourceType, setup-matt-pocock-skills

### Community 61 - "Community 61"
Cohesion: 0.40
Nodes (5): to-issues, computedHash, skillPath, source, sourceType

### Community 62 - "Community 62"
Cohesion: 0.40
Nodes (5): write-a-skill, computedHash, skillPath, source, sourceType

### Community 63 - "Community 63"
Cohesion: 0.40
Nodes (5): tdd, computedHash, skillPath, source, sourceType

### Community 64 - "Community 64"
Cohesion: 0.40
Nodes (5): to-prd, computedHash, skillPath, source, sourceType

### Community 65 - "Community 65"
Cohesion: 0.40
Nodes (5): Common Rules for Professional UI, Icons & Visual Elements, Interaction (App), Layout & Spacing, Light/Dark Mode Contrast

### Community 66 - "Community 66"
Cohesion: 0.40
Nodes (5): Example Workflow, Step 1: Analyze Requirements, Step 2: Generate Design System (REQUIRED), Step 3: Supplement with Detailed Searches (as needed), Step 4: Stack Guidelines

### Community 67 - "Community 67"
Cohesion: 0.50
Nodes (3): Expanding the ESLint configuration, React Compiler, React + TypeScript + Vite

### Community 68 - "Community 68"
Cohesion: 0.83
Nodes (3): hitl-loop.template.sh script, capture(), step()

### Community 69 - "Community 69"
Cohesion: 0.50
Nodes (3): Bad Tests, Good and Bad Tests, Good Tests

### Community 70 - "Community 70"
Cohesion: 0.50
Nodes (4): Common Sticking Points, Pre-Delivery Checklist, Query Strategy, Tips for Better Results

### Community 71 - "Community 71"
Cohesion: 0.50
Nodes (4): Must Use, Recommended, Skip, When to Apply

## Knowledge Gaps
- **441 isolated node(s):** `version`, `source`, `sourceType`, `skillPath`, `computedHash` (+436 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GitHubIssueRecord` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 9`, `Community 12`, `Community 13`, `Community 14`, `Community 29`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `datetime` connect `Community 0` to `Community 1`, `Community 4`, `Community 9`, `Community 13`, `Community 17`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `Orchestrator` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 7`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 97 inferred relationships involving `GitHubIssue` (e.g. with `Any` and `BackgroundTaskScheduler`) actually correct?**
  _`GitHubIssue` has 97 INFERRED edges - model-reasoned connections that need verification._
- **Are the 92 inferred relationships involving `GitHubIssueRecord` (e.g. with `ExecutionResult` and `HarnessExecutionService`) actually correct?**
  _`GitHubIssueRecord` has 92 INFERRED edges - model-reasoned connections that need verification._
- **Are the 66 inferred relationships involving `GitHubIssueGateway` (e.g. with `Any` and `ArgumentParser`) actually correct?**
  _`GitHubIssueGateway` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 71 inferred relationships involving `PrdIssue` (e.g. with `Any` and `ClaimError`) actually correct?**
  _`PrdIssue` has 71 INFERRED edges - model-reasoned connections that need verification._