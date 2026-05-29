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
An Implementation Issue that has been reserved for exactly one agent run. It is no longer eligible for other agents to claim while that run is active.
_Avoid_: Picked-up ticket, assigned issue, locked task

**Failed Implementation Issue**:
An Implementation Issue that an agent attempted but did not complete. It requires human review before it can become ready for autonomous execution again.
_Avoid_: Retriable ticket, errored task, stuck issue

**Agent Run**:
A single autonomous attempt to complete one Claimed Implementation Issue. An Agent Run either completes the issue or leaves it as a Failed Implementation Issue.
_Avoid_: Agent session, worker job, execution

**Agent Harness**:
The executable adapter that performs an Agent Run for a Claimed Implementation Issue. The orchestrator selects an Agent Harness, but the harness owns the coding-agent behavior.
_Avoid_: Agent, worker, runner

**Integrated Implementation Issue**:
An Implementation Issue that has had its successful Agent Run commits merged back into its Parent PRD's PRD branch and has been closed.
_Avoid_: Completed ticket, merged issue, done task

