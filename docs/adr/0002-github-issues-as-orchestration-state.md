# Use GitHub Issues as orchestration state

The orchestrator stores lifecycle state in GitHub Issues, labels, branches, and worktrees instead of introducing a separate database for v1. PRD Issues carry preparation metadata such as the PRD branch, and Implementation Issues carry claim metadata such as claim time, agent run identity, and implementation branch. This keeps the system recoverable from the repository and issue tracker while avoiding a second state store until analytics or stronger leasing justify it.
