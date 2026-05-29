# rangkai

> **rangkai** *(pronounced: "rUNG-kye", /raŋ.kaɪ/)*
>
>to connect, link together, arrange into a sequence, or assemble separate parts into a unified whole.
>

Standalone Python orchestration system for running coding agents against GitHub Issues.

Rangkai uses GitHub Issues, labels, branches, worktrees, and local run-state files as orchestration state. PRD Issues define product-level work, Implementation Issues define executable agent work, and Agent Runs execute claimed Implementation Issues through a configured Agent Harness.

## Install

### Prerequisites

You need:
- `git`
- GitHub CLI `gh`, authenticated for the target repository
- The Agent Harness command configured in `bersama.yaml`, such as `codex`

### Local Installation

From the repository root directory, install in editable mode with development dependencies:

Using `uv` (recommended):
```bash
uv pip install -e ".[dev]"
```

Or using standard `pip`:
```bash
python -m pip install -e ".[dev]"
```

## Configure

Bersama reads `bersama.yaml` from the current directory by default. Pass `--config path/to/bersama.yaml` to use another file.

```yaml
harnesses:
  codex-headless:
    command: codex
    args_template:
      - exec
      - "--dangerously-bypass-approvals-and-sandbox"
      - "$tdd solve issue #{issue_number} on github and commit once execution is complete"

repos:
  bersama:
    repo_path: /home/me/src/bersama
    main_branch: main
    worktree_root: /home/me/src/bersama/worktrees
    global_concurrency: 2
    per_prd_concurrency: 1
    default_harness: codex-headless
```

Available harness template variables include:

- `{repo_name}`
- `{repo_path}`
- `{main_branch}`
- `{worktree_root}`
- `{global_concurrency}`
- `{per_prd_concurrency}`
- `{harness_name}`
- `{issue_number}`
- `{parent_prd_number}`
- `{prd_branch}`
- `{implementation_branch}`

## Run The Dashboard

The dashboard provides a visual cockpit showing repositories, issues, Agent Runs, and harness logs.

### Running with a Pre-built Production UI (Single Port)

This compiles the React frontend once and serves both frontend assets and FastAPI endpoints on a single port (8000 by default).

1. **Build the frontend**:
   ```bash
   cd dashboard
   npm install
   npm run build
   cd ..
   ```

2. **Start the dashboard server**:
   ```bash
   # Using uv (recommended)
   uv run bersama dashboard --config bersama.yaml --host 127.0.0.1 --port 8000

   # Or using standard python/global CLI
   bersama dashboard --config bersama.yaml --host 127.0.0.1 --port 8000
   ```

3. **Open**: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Running with Hot-Reloading for Development (Two Ports)

This runs the backend API and the Vite frontend dev server concurrently, allowing hot-reloading (HMR) for frontend code modifications.

1. **Start the backend API (Port 8000)**:
   ```bash
   # Using uv (recommended)
   uv run bersama dashboard --config bersama.yaml --host 127.0.0.1 --port 8000

   # Or using standard python/global CLI
   bersama dashboard --config bersama.yaml --host 127.0.0.1 --port 8000
   ```

2. **Start the Vite dev server (Port 5173 by default) in a separate terminal**:
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```

3. **Open**: [http://localhost:5173](http://localhost:5173) (or the port specified by Vite). The frontend automatically routes API requests to the backend running on port 8000.

### Read-Only API Endpoints

The backend exposes read APIs:

```bash
curl http://127.0.0.1:8000/api/repos
curl "http://127.0.0.1:8000/api/issues?repo=bersama"
curl "http://127.0.0.1:8000/api/runs?repo=bersama"
curl "http://127.0.0.1:8000/api/runs/123/log?repo=bersama&limit=100"
```

## Run The Orchestration System

You can run the CLI commands using `uv run bersama`, `python -m bersama`, or directly as `bersama` if the package is installed in your active environment/global PATH.

Run one orchestration pass for a configured repository:

```bash
# Using uv (recommended)
uv run bersama run bersama --config bersama.yaml

# Or using standard python/global CLI
bersama run bersama --config bersama.yaml
```

Run continuously until no more Implementation Issues are claimable:

```bash
# Using uv (recommended)
uv run bersama run bersama --config bersama.yaml --continuous

# Or using standard python/global CLI
bersama run bersama --config bersama.yaml --continuous
```

The orchestrator will:

1. Reconcile issue lifecycle state.
2. Prepare open PRD Issues that do not yet have PRD branch metadata.
3. Plan claimable Ready Implementation Issues using configured concurrency limits.
4. Claim each selected Implementation Issue and create an isolated worktree.
5. Execute the configured Agent Harness for each Claimed Implementation Issue.
6. Integrate successful Agent Runs back into the Parent PRD branch.
7. Reconcile state again.

## Manual Operations

Use these commands when you want operator control over one step at a time. Prefix them with `uv run` if executing within a local development workspace.

Reconcile issue state:
```bash
uv run bersama reconcile bersama --config bersama.yaml
```

Prepare a PRD Issue:
```bash
uv run bersama prepare-prd bersama 15 --config bersama.yaml
```

Claim a Ready Implementation Issue:
```bash
uv run bersama claim-issue bersama 16 --agent-run-id run-manual-001 --config bersama.yaml
```

Execute the Agent Harness for a Claimed Implementation Issue:
```bash
uv run bersama execute-run bersama 16 --config bersama.yaml
```

Integrate a successful Agent Run into its Parent PRD branch:
```bash
uv run bersama integrate-run bersama 16 --config bersama.yaml
```

## Issue Requirements

For autonomous execution, an Implementation Issue must:

- Have the `implementation` label.
- Have the `ready-for-agent` label.
- Declare exactly one Parent PRD.
- Have no open Blocking Dependencies.
- Belong to a Prepared PRD Issue.

A PRD Issue must have the `prd` label. Preparing it records PRD branch metadata in the issue body.
