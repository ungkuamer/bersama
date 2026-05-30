# Lock shared repository operations

Concurrent Agent Runs may execute in separate worktrees, but orchestration operations that mutate shared repository metadata are guarded by a process-local Repository Operation Lock. This keeps harness execution parallel while preventing races around `git fetch`, branch creation, worktree add/remove, and PRD branch integration; the alternative of serializing the whole orchestrator would unnecessarily reduce Agent Run throughput.
