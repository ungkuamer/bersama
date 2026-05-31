# Social Media Post Drafts for Bersama / Rangkai

This document contains drafts for LinkedIn (Builder-focused, professional yet casual) and X/Threads (Casual, punchy English, highly relatable for developers).

---

## 👔 LinkedIn Post (Option 2: The "Builder's Insight" Style)

I've been building a project called **bersama** (orchestrated via **rangkai**). 

It is a lightweight Python orchestrator that uses **GitHub Issues, labels, branches, and worktrees as the orchestration state machine.**

Instead of reinventing the wheel, the state of the agent run is tracked by standard GitHub tags (`prd`, `implementation`, `ready-for-agent`). If a task is blocked, it's explicitly declared in the issue tracker. If an agent fails, the issue is flagged for human review.

The workflow is highly opinionated, moving from:
👉 **Grill Session** (Powered by our custom `/grill-me` and `/grill-with-docs` skills. The AI acts as a relentless interviewer, challenging the design against our domain model, and updating `CONTEXT.md` and ADRs inline as decisions crystallize.)
👉 **PRD Creation** (Powered by our `/to-prd` skill. It translates the conversation's shared understanding directly into a structured Product Requirements Document and automatically publishes it as a GitHub PRD issue.)
👉 **Task Breakdown** (Powered by our `/to-issues` skill. It breaks down the PRD issue into independent "tracer-bullet" vertical slices—Implementation Issues—mapping precise dependency tags directly on the tracker.)
👉 **TDD Implementation** (agents solve claimed issues using a strict Test-Driven Development loop—writing public-interface tests first, writing minimal code to pass, and refactoring under a clean green light)

Why is this different from other tools? 

Instead of using proprietary agent dashboards, complex databases, or custom workflow state files, **the single source of truth is just Git and GitHub**. 

Issue labels, branches, and worktrees drive the entire run-state. If a task is blocked, it's explicitly declared on GitHub. If an agent fails, it requires human triage exactly like a broken CI check. Plus, by isolating execution into local git worktrees and enforcing a strict TDD loop, agents can't silently pollute your main working directory or push untested code.

The goal isn't to replace developers. The goal is to build a high-fidelity bridge between human product planning and autonomous, test-driven execution. 

The project is still in active development (plenty of rough edges and incomplete features!), but the core loop is already running. I'll be sharing updates, architectural decisions, and demo runs as I continue developing it.

Let me know what you think of this approach! Do you prefer integrated workflows like this, or do you like using standalone AI coding tools?

#CodingAgents #TDD #SoftwareArchitecture #GitHub #LangGraph #React #FastAPI #BuildInPublic

---

## 🐦 X / Threads Draft (Casual English Builder Style)
*This is written as a punchy thread to fit perfectly on X or Threads, using natural, casual English.*

***

**[TWEET 1 / POST 1]**
AI coding agents are great, but let’s be real: without proper planning, your codebase turns into a total mess. 🫠 

It’s painful when an agent starts writing code that completely drifts from the actual specs.

So I started building: **bersama** (orchestrator: **rangkai**). 

Thread below on why it’s different 👇

**[TWEET 2 / POST 2]**
It’s a lightweight Python agent orchestrator using GitHub Issues & worktrees as the state machine. 

The workflow is highly opinionated, moving from:
1️⃣ **Grill Session 🎙️** - Driven by custom `/grill-me` & `/grill-with-docs` skills. The AI relentlessly interviews you to stress-test your design against the domain glossary & updates your ADRs inline.
2️⃣ **PRD Issue 📄** - Driven by our `/to-prd` skill. Automatically packages that alignment into a structured PRD issue on GitHub.

**[TWEET 3 / POST 3]**
3️⃣ **Task Breakdown 🎯** - Driven by our `/to-issues` skill. Decomposes the PRD into independent "tracer-bullet" implementation tasks with explicit dependency tags (e.g., Task B blocked by Task A).
4️⃣ **TDD Implementation 🧪** - Agents claim tasks and solve them using a strict Test-Driven Development (Red-Green-Refactor) loop.

**[TWEET 4 / POST 4]**
Why is this different from existing tools?

Because **the single source of truth is just Git and GitHub**. 

No proprietary databases or bloated custom dashboards. State is tracked via GitHub labels, branches & worktrees. Agent failed? It’s treated exactly like a broken CI check requiring human triage.

**[TWEET 5 / POST 5]**
Isolated execution in Git worktrees also means agents can't silently pollute your main working directory or push untested code.

It's still very much a work-in-progress, but the core loop is running. I'll be sharing updates & demos as I build. 

How do you orchestrate your agent pipelines? Let's discuss! 👇

***

## 💡 Recommendations for Posting

* **Tone**: The casual English keeps it incredibly clean, authentic, and direct. Developer circles on X/Threads value actual engineering detail and simplicity over hype.
* **Media**: Attaching a clean screenshot of the local React dashboard or a quick terminal execution log will significantly boost engagement on X/Threads.
