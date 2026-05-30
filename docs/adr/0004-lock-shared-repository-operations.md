# Lock shared repository operations

Concurrent Agent Runs may execute in separate worktrees, but orchestration operations that mutate shared repository metadata are guarded by a system-wide file-based Repository Operation Lock (``fcntl.flock``) bound to the repository directory. This keeps harness execution parallel while preventing races around `git fetch`, branch creation, worktree add/remove, and PRD branch integration across concurrent CLI and dashboard processes; the alternative of serializing the whole orchestrator would unnecessarily reduce Agent Run throughput.
