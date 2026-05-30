# Serialize PRD branch integration

Concurrent Agent Runs may execute at the same time in separate worktrees and implementation branches, but successful Integration Issues are merged back into their Parent PRD branch one at a time. The PRD branch is the shared feature-level integration point, so serializing integration avoids push races, non-deterministic merge ordering, and harder-to-debug conflicts while still allowing autonomous implementation work to run in parallel.
