# Use pnpm for dashboard dependency sharing

The dashboard uses pnpm instead of npm so isolated agent worktrees can keep independent `node_modules` layouts while sharing package bytes through pnpm's content-addressable store. Dependency installation remains a tooling concern rather than part of Claim Setup, because making worktree creation depend on Node registry access would increase failed claims and blur orchestration lifecycle boundaries. Shared build-output caching is intentionally deferred until build time, not dependency storage, becomes a measured bottleneck.
