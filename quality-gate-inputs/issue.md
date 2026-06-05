# Build LangGraph agent orchestration system

Issue: https://github.com/ungkuamer/rangkai/issues/1

## Problem Statement

Today, autonomous implementation work is coordinated manually. A human creates a PRD Issue, creates child Implementation Issues, checks which issues are unblocked, prompts an agent with a command such as `tdd github issue #123`, waits for the result, pushes or integrates the work, closes completed issues, and repeats the loop until the PRD is ready for human review.

This manual coordination limits throughput, makes parallel agent execution difficult, and leaves too much lifecycle state in the human operator's head. The user wants a standalone orchestrator that can inspect GitHub Issues, identify Ready Implementation Issues, run the appropriate Agent Harness, integrate completed work through PRD branches, and provide a local dashboard showing what each Agent Run is doing.

## Solution

Build a standalone Python and LangGraph-based agent orchestration system for one target repository per running instance. The orchestrator will use `gh` and `git` to manage GitHub Issues, branches, worktrees, labels, and lifecycle transitions. It will consume PRD Issues and Implementation Issues that humans already created; it will not decompose PRDs into child issues in v1.

Each PRD Issue will be prepared with a PRD branch. Each Ready Implementation Issue will be claimed, assigned its own implementation branch from the PRD branch, executed by the configured default Agent Harness, and merged back into the PRD branch if the harness succeeds and creates at least one new commit. Successful child issues close silently. Failures move to `needs-triage` or `needs-info` with concise diagnostic comments. When all child Implementation Issues for a PRD Issue are closed, the PRD Issue receives `ready-for-human` and remains open for manual human review and merge to `main`.

The system will include a read-only local dashboard backed by FastAPI and a React/Vite frontend using shadcn/ui, Tailwind, mono typography, monochrome styling, and minimal color. The dashboard will poll for status, show PRD Issues, Implementation Issues, Agent Runs, branches, failures, and local log tails.

## User Stories

1. As a maintainer, I want the orchestrator to find Ready Implementation Issues automatically, so that I do not have to manually scan GitHub Issues for agent-ready work.
2. As a maintainer, I want each Implementation Issue to declare exactly one Parent PRD, so that agent work is grouped under the correct feature-level context.
3. As a maintainer, I want the orchestrator to read Blocking Dependencies from issue bodies, so that agents only start work whose prerequisites are complete.
4. As a maintainer, I want malformed Implementation Issues to be moved to `needs-info`, so that incomplete work items do not get attempted by agents.
5. As a maintainer, I want invalid or failed agent work to be moved to `needs-triage`, so that human review is required before another attempt.
6. As a maintainer, I want PRD Issues to be prepared with PRD branches automatically, so that I can keep manually creating PRDs without remembering branch setup.
7. As a maintainer, I want child Implementation Issues to run on implementation branches created from their PRD branch, so that each agent has isolated working space.
8. As a maintainer, I want successful implementation branches to merge back into the PRD branch, so that feature-level integration accumulates in one branch.
9. As a maintainer, I want the PRD branch to be merged to `main` by a human, so that final integration remains under human control.
10. As a maintainer, I want child Implementation Issues to close after successful merge into the PRD branch, so that completed agent work disappears from the active queue.
11. As a maintainer, I want PRD Issues to receive `ready-for-human` after all children are closed, so that I know the feature branch is ready to review.
12. As a maintainer, I want PRD Issues to remain open until I manually close them, so that final feature acceptance is explicit.
13. As a maintainer, I want the orchestrator to run only when I invoke the CLI command, so that background automation does not spend tokens or mutate repositories unexpectedly.
14. As a maintainer, I want global and per-PRD concurrency limits, so that multiple agents can run without overwhelming local resources or one PRD monopolizing capacity.
15. As a maintainer, I want agents under the same PRD to run in parallel when dependencies allow, so that independent implementation work finishes faster.
16. As a maintainer, I want merge conflicts to fail the relevant Implementation Issue, so that conflicts are handled deliberately rather than hidden.
17. As a maintainer, I want the orchestrator to rely on merge conflict detection instead of precomputing file overlap, so that v1 stays simple and avoids inaccurate predictions.
18. As a maintainer, I want the Agent Harness to be configurable, so that I can swap the headless coding agent without rewriting orchestration logic.
19. As a maintainer, I want v1 to use one default Agent Harness from config, so that harness selection remains simple at first.
20. As a maintainer, I want the Agent Harness to commit locally and avoid GitHub lifecycle side effects, so that all issue and branch state transitions are consistent.
21. As a maintainer, I want the orchestrator to push, merge, label, comment on failure, and close issues, so that GitHub state has one owner.
22. As a maintainer, I want the orchestrator to treat harness success as exit code `0` plus at least one new local commit, so that false-positive runs are caught.
23. As a maintainer, I want the harness to own test execution, so that different harnesses can apply the right validation without a central validation command.
24. As a maintainer, I want TDD to live in the default harness prompt rather than orchestration logic, so that the orchestrator remains method-agnostic.
25. As a maintainer, I want local logs captured for each Agent Run, so that I can inspect what happened without filling GitHub Issues with noisy output.
26. As a maintainer, I want failure comments to be concise and durable in GitHub, so that failed work can be triaged even if local logs are later removed.
27. As a maintainer, I want GitHub Issues, labels, branches, and worktrees to be the durable state for v1, so that no separate database is required.
28. As a maintainer, I want local JSON run-state files, so that the dashboard can show live status while GitHub remains the recovery source of truth.
29. As a maintainer, I want stale claimed issues to be detected after timeout, so that crashes do not leave work permanently in progress.
30. As a maintainer, I want interrupted Agent Runs to become stale rather than resume automatically, so that unsafe process recovery is avoided in v1.
31. As a maintainer, I want a read-only dashboard, so that I can observe the system without introducing dashboard-driven lifecycle mutations.
32. As a maintainer, I want the dashboard to run locally, so that no hosted service, authentication layer, or remote access model is required for v1.
33. As a maintainer, I want dashboard status to update by polling, so that live visibility is available without WebSocket complexity.
34. As a maintainer, I want the dashboard to show PRD Issues and their child Implementation Issues, so that I can understand feature-level progress quickly.
35. As a maintainer, I want the dashboard to show active Agent Runs, so that I can see which issue each harness is currently working on.
36. As a maintainer, I want the dashboard to show branch names and run IDs, so that I can connect UI status to git state and local logs.
37. As a maintainer, I want the dashboard to show failure reasons, so that I can decide what to triage next.
38. As a maintainer, I want the dashboard to show local log tails, so that I can inspect recent harness output without opening files manually.
39. As a maintainer, I want minimal monochrome dashboard styling, so that the UI stays operational and information-dense rather than decorative.
40. As a maintainer, I want YAML configuration for repo and harness settings, so that I can adjust paths, branches, concurrency, and harness commands without code changes.
41. As a maintainer, I want credentials to stay in existing `gh` and git authentication, so that the orchestrator does not manage secrets in config.
42. As a maintainer, I want v1 to manage one target repo per run, so that scheduling, worktrees, dashboard filtering, and failure handling stay clear.
43. As a maintainer, I want the tool to be standalone, so that orchestration machinery does not have to live inside each target product repo.
44. As a maintainer, I want issue body headings to be canonical, so that parsing is reliable and issue templates are predictable.
45. As a maintainer, I want successful issues to close without success comments, so that issue timelines stay quiet and useful.

## Implementation Decisions

- Build the orchestrator as a standalone Python project using LangGraph for workflow coordination.
- Scope v1 to one configured target repository per running orchestrator instance.
- Use `gh` CLI and local `git` commands for GitHub and repository operations.
- Store configuration in YAML, including target repo path, main branch, worktree root, global concurrency, per-PRD concurrency, and default Agent Harness command/template.
- Do not store secrets in orchestrator config; rely on existing `gh` and git authentication.
- Consume human-created PRD Issues and Implementation Issues only; do not automatically decompose PRDs into child issues in v1.
- Identify PRD Issues with a `prd` label and Implementation Issues with an `implementation` label.
- Apply `ready-for-agent` only to Implementation Issues, not PRD Issues.
- Require Implementation Issues to use canonical Markdown sections: `Parent PRD`, `What to Build`, `Acceptance Criteria`, and `Blocked By`.
- Require `Parent PRD` to contain exactly one issue reference.
- Allow `Blocked By` to be empty or contain issue references.
- Treat cross-PRD Blocking Dependencies as invalid data, even though they are not expected in normal use.
- Use a PRD preparation step that creates and pushes a PRD branch if missing, then records orchestration metadata in the PRD Issue body.
- Name PRD branches as `prd/<prd-issue-number>-<slug>`.
- Name implementation branches as `impl/<prd-issue-number>/<implementation-issue-number>-<slug>`.
- Claim Ready Implementation Issues by moving them from `ready-for-agent` to an in-progress agent label before launching a harness.
- Write claim metadata into an `Orchestration` section of the Implementation Issue body, including claim time, Agent Run identity, and implementation branch.
- Use GitHub Issues, labels, branches, and worktrees as durable orchestration state for v1.
- Use local run-state JSON files and local log files for dashboard-visible live state.
- Avoid a separate database in v1.
- Create isolated worktrees and implementation branches for each Agent Run.
- Use the current PRD branch as the base for each implementation branch.
- Run multiple Ready Implementation Issues in parallel according to global and per-PRD concurrency limits.
- Do not precompute file overlap; rely on rebase/merge conflict detection before integrating implementation branches.
- Before merging successful work, update the implementation branch against the latest PRD branch and fail the issue if integration conflicts occur.
- Treat harness success as a zero exit code plus at least one new local commit compared with the PRD branch.
- Do not require commit messages to mention the issue number in v1.
- Do not run a central validation command after harness completion; the Agent Harness is responsible for its own checks and tests.
- Keep TDD as part of the default Agent Harness prompt, not as orchestrator logic.
- Restrict GitHub side effects to the orchestrator. The Agent Harness modifies files, runs checks, and creates local commits only.
- On success, the orchestrator pushes the implementation branch, merges it into the PRD branch, and closes the Implementation Issue without a success comment.
- On harness failure, branch setup failure, stale claim timeout, or merge conflict, move the Implementation Issue to `needs-triage` and add a concise diagnostic comment.
- On malformed required sections, move the Implementation Issue to `needs-info` and comment with the missing or invalid sections.
- When all child Implementation Issues for a PRD Issue are closed, add `ready-for-human` to the PRD Issue and leave it open.
- Do not auto-close PRD Issues in v1. Human review and merge to `main` remain manual.
- Provide an explicit CLI run command that performs one orchestration cycle and exits.
- Provide a local read-only dashboard as a separate long-running mode or service.
- Build the dashboard backend with FastAPI.
- Build the dashboard frontend with React/Vite, shadcn/ui, Tailwind, mono font, monochrome palette, and minimal styling.
- Use polling for dashboard updates in v1.
- Show PRD Issues, Implementation Issues, Agent Runs, branches, failure states, and local log tails in the dashboard.
- Defer dashboard write actions such as requeueing, stopping, or marking ready.

## Testing Decisions

- Tests should focus on external behavior and lifecycle outcomes rather than LangGraph internals or subprocess implementation details.
- The Issue Model and Parser should have extensive unit tests for valid PRD Issues, valid Implementation Issues, missing sections, malformed `Parent PRD`, malformed `Blocked By`, cross-PRD dependencies, labels, orchestration metadata, and diagnostic messages.
- The Orchestration Planner should have extensive unit tests for PRD preparation decisions, Ready Implementation Issue eligibility, Blocking Dependency handling, concurrency limits, malformed issue handling, stale claim handling, all-children-closed detection, and failure transitions.
- The Configuration Loader should have unit tests for valid YAML, missing required fields, harness command templates, concurrency defaults, and path settings.
- GitHub Issue Gateway behavior should be tested with fake command runners so lifecycle commands can be verified without contacting GitHub in normal test runs.
- Git Workspace Gateway behavior should be tested with fake command runners for command construction and with temporary git repositories for branch/worktree integration where valuable.
- Agent Harness Executor should be integration-tested with temporary git repositories and tiny fake harness commands that succeed, fail, create commits, or exit successfully without commits.
- Run State Store should be unit-tested for JSON state writes, updates, stale run representation, and log path handling.
- Dashboard Backend should have API tests against representative PRD, Implementation Issue, Agent Run, failure, and log-tail data.
- Dashboard Frontend tests can be light in v1 and should focus on rendering the key read-only states without depending on visual implementation details.
- No real GitHub network calls should be required for the default automated test suite.

## Out of Scope

- Automatically decomposing PRD Issues into Implementation Issues.
- Running multiple target repositories in one orchestrator instance.
- Hosting the dashboard remotely.
- Authentication or multi-user authorization for the dashboard.
- Dashboard write actions such as requeue, stop, retry, edit labels, or mark ready.
- Auto-closing PRD Issues after merge to `main`.
- Auto-merging PRD branches to `main`.
- Central validation commands owned by the orchestrator.
- Predicting file overlap before agents run.
- Resuming interrupted harness processes after orchestrator restart.
- Using a separate database for v1 orchestration state.
- Harness selection labels or rule-based harness routing beyond one configured default harness.
- Enforcing commit message formats.
- Full historical analytics for Agent Runs.

## Further Notes

This PRD follows the resolved glossary in `CONTEXT.md` and the branch/state ADRs. The core architectural split is that the orchestrator owns scheduling and lifecycle state, while the Agent Harness owns the coding-agent behavior for one Claimed Implementation Issue. The MVP should prove the full loop from existing GitHub Issues to PRD branch integration before adding planner automation, richer routing, dashboard controls, or hosted monitoring.

## Orchestration
- PRD Branch: prd/1-build-langgraph-agent-orchestration-system
