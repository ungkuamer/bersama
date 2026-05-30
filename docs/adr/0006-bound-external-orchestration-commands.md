# Bound external orchestration commands

External `gh` and `git` commands are bounded by phase-aware timeouts and retries instead of being allowed to block indefinitely. Discovery Operations use short timeouts with limited retries because they do not change lifecycle state, while Lifecycle Mutations use longer timeouts and only retry when idempotency can be verified by preflight or postflight checks; Agent Harness execution remains governed by harness-specific timeout configuration.
