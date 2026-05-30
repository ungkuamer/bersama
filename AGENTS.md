## Agent skills

### Issue tracker

Issues live in GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Knowledge graph (graphify)

The project has a graphify knowledge graph at `graphify-out/`. Use for codebase questions:
- `graphify query "<question>"` — BFS traversal
- `graphify path "<node>" "<node>"` — shortest path
- `graphify explain "<node>"` — explain a concept
- `graphify update .` — rebuild after code changes (no API cost)

See `.pi/agent/skills/graphify/SKILL.md` for full `/graphify` usage.
