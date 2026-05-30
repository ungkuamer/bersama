# Agent Orchestration

This context describes how autonomous agents select and complete GitHub issue work derived from product planning.

## Language

**PRD Issue**:
A GitHub issue that describes a planned feature or change at product-requirements level. It is identified by the `prd` label, provides context for child work, and is not executed directly by agents.
_Avoid_: Parent ticket, feature ticket, planning issue

**Prepared PRD Issue**:
A PRD Issue that has the orchestration metadata needed for child Implementation Issues to run. A PRD Issue must be prepared before its child work can be claimed.
_Avoid_: Initialized PRD, active PRD, branched PRD

**Implementation Issue**:
A GitHub issue that represents one executable unit of engineering work for an agent. It is identified by the `implementation` label, belongs to a PRD Issue, and contains enough detail for the agent to complete it independently.
_Avoid_: Ticket, sub-issue, task

**Parent PRD**:
The PRD Issue that owns an Implementation Issue. Each Implementation Issue declares exactly one Parent PRD.
_Avoid_: Parent ticket, epic, umbrella issue

**Ready Implementation Issue**:
An Implementation Issue that is eligible for autonomous execution. It has the `ready-for-agent` label and is not blocked by any open Implementation Issue.
_Avoid_: Non-blocked issue, available ticket, runnable task

**Blocking Dependency**:
An open Implementation Issue that must be completed before another Implementation Issue can be executed. Blocking Dependencies are declared in the blocked issue's `Blocked by` field.
_Avoid_: Dependency, prerequisite, blocker

**Claimed Implementation Issue**:
An Implementation Issue that has been reserved for exactly one Agent Run that is ready to start immediately. It is no longer eligible for other agents to claim while that run is active.
_Avoid_: Picked-up ticket, assigned issue, locked task

**Claim Setup**:
The transition during which a Ready Implementation Issue is being reserved for an Agent Run. It is not yet a Claimed Implementation Issue because the Agent Run is not ready to start immediately.
_Avoid_: Partial claim, half-claimed issue, pre-claim

**Active Claim**:
A Claim Setup that has successfully become a Claimed Implementation Issue. The owning Agent Run has the repository state it needs to begin execution.
_Avoid_: Final claim, confirmed claim, locked issue

**Failed Claim Setup**:
A Claim Setup that did not become an Active Claim. The Implementation Issue requires human review before another Agent Run can claim it.
_Avoid_: Broken claim, abandoned setup, failed reservation

**Stale Claim**:
A claim on an Implementation Issue whose Agent Run is no longer considered active because its claim metadata is older than the configured timeout.
_Avoid_: Dead job, abandoned task, orphaned worker

**Failed Implementation Issue**:
An Implementation Issue that an agent attempted but did not complete, including cases where its Agent Run succeeded but integration into the Parent PRD branch failed. It requires human review before it can become ready for autonomous execution again.
_Avoid_: Retriable ticket, errored task, stuck issue

**Agent Run**:
A single autonomous attempt to complete one Claimed Implementation Issue. An Agent Run either completes the issue or leaves it as a Failed Implementation Issue.
_Avoid_: Agent session, worker job, execution

**Concurrent Agent Run**:
An Agent Run that executes at the same time as another Agent Run in the same orchestrator process.
_Avoid_: Parallel task, worker task, background job

**Agent Run Capacity**:
The number of Agent Runs that may execute at the same time. Agent Run Capacity is separate from serialized integration into a Parent PRD branch.
_Avoid_: Queue capacity, worker count, integration capacity

**Agent Harness**:
The executable adapter that performs an Agent Run for a Claimed Implementation Issue. The orchestrator selects an Agent Harness, but the harness owns the coding-agent behavior.
_Avoid_: Agent, worker, runner

**Execution Scheduler**:
The orchestration component that selects Ready Implementation Issues and starts Agent Runs within configured concurrency limits.
_Avoid_: Task queue, worker pool, job scheduler

**Scheduling Pass**:
One evaluation of Implementation Issue state that selects Ready Implementation Issues for available Agent Run capacity.
_Avoid_: Queue polling, batch, sweep

**Discovery Operation**:
A read-only orchestration operation that observes GitHub Issues, git references, worktrees, or Integration Pull Request status without changing lifecycle state.
_Avoid_: Read step, lookup, scan

**Lifecycle Mutation**:
An orchestration operation that changes issue lifecycle state, claim state, repository branches, worktrees, or Integration Pull Request state.
_Avoid_: Write step, update, side effect

**Repository Operation Lock**:
A system-wide file-based guard that prevents concurrent orchestration processes from mutating the same repository metadata at the same time.
_Avoid_: Global lock, worker lock, queue lock

**Integration Pull Request**:
A GitHub Pull Request created programmatically by the orchestrator to merge the successful commits of an Agent Run's implementation branch into its Parent PRD's PRD branch.
_Avoid_: Pull Request, PR, merge request

**Integrated Implementation Issue**:
An Implementation Issue that has had its successful Agent Run commits merged back into its Parent PRD's PRD branch via an Integration Pull Request and has been closed.
_Avoid_: Completed ticket, merged issue, done task

**Orchestration Control Center**:
The human-facing dashboard for inspecting PRD Issue and Implementation Issue state, triggering orchestration operations, and reviewing Agent Run logs.
_Avoid_: Admin panel, scaffold dashboard, cockpit
