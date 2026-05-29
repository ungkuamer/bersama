# bersama

Standalone Python orchestrator scaffold with YAML configuration and a config-driven CLI.

## CLI

```bash
bersama run <repo-name> --config path/to/config.yaml
```

## Configuration

```yaml
harnesses:
  local-agent:
    command: codex
    args_template:
      - "run"
      - "--repo"
      - "{repo_path}"

repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    global_concurrency: 2
    per_prd_concurrency: 1
    default_harness: local-agent
```
