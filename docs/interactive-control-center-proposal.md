# Interactive Agent Control Center & Zero-Config Packaging Proposal

This document acts as a unified technical blueprint for transforming the **Bersama Orchestration System** into a premium, interactive web cockpit that can be installed globally and run on any Git repository with **zero configuration**.

---

## Part 1: Interactive Cockpit API & UX Design

Currently, the Bersama dashboard is a read-only viewer. Exposing the core command operations via REST APIs on the FastAPI backend enables immediate execution, claiming, and reconciliation directly from the React dashboard.

### 1. Unified Backend Architecture (`src/bersama/dashboard.py`)

To ensure robustness, the dashboard executes operations in two ways:
* **Synchronous (Instant)**: Operations like Reconciliation, PRD Branch Preparation, and Branch Integration complete in under a second and return HTTP `200 OK`.
* **Asynchronous (Background)**: Harness Execution runs via FastAPI's `BackgroundTasks` so the HTTP thread returns a `202 Accepted` immediately, avoiding browser timeouts.

#### Proposed Code Additions:
```python
from pydantic import BaseModel
from fastapi import BackgroundTasks
from pathlib import Path

# Pydantic schema for claiming
class ClaimRequest(BaseModel):
    agent_run_id: str

# 1. State Reconciliation
@app.post("/api/reconcile")
def reconcile_issues(repo: str | None = None) -> dict[str, Any]:
    repo_cfg = get_repo_config(repo)
    active_gateway = issues_gateway or GitHubIssueGateway(cwd=repo_cfg.repo_path)
    service = ReconciliationService(issues=active_gateway)
    try:
        service.reconcile()
        return {"status": "success", "message": "States reconciled successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. PRD Preparation
@app.post("/api/issues/{issue_number}/prepare")
def prepare_prd(issue_number: int, repo: str | None = None) -> dict[str, Any]:
    repo_cfg = get_repo_config(repo)
    active_gateway = issues_gateway or GitHubIssueGateway(cwd=repo_cfg.repo_path)
    service = PrdPreparationService(issues=active_gateway, workspace=GitWorkspaceGateway())
    try:
        result = service.prepare_issue(
            repo_path=str(repo_cfg.repo_path),
            main_branch=repo_cfg.main_branch,
            issue_number=issue_number,
        )
        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)
        return {
            "status": "success", 
            "prd_branch": result.prd_branch, 
            "reused": result.reused_existing_branch
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Issue Claiming & Isolated Worktree Setup
@app.post("/api/issues/{issue_number}/claim")
def claim_issue(issue_number: int, request: ClaimRequest, repo: str | None = None) -> dict[str, Any]:
    repo_cfg = get_repo_config(repo)
    active_gateway = issues_gateway or GitHubIssueGateway(cwd=repo_cfg.repo_path)
    service = ImplementationClaimService(issues=active_gateway, workspace=ClaimWorkspaceGateway())
    try:
        result = service.claim_issue(
            repo_path=str(repo_cfg.repo_path),
            worktree_root=str(repo_cfg.worktree_root),
            issue_number=issue_number,
            agent_run_id=request.agent_run_id,
        )
        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)
        return {
            "status": "success", 
            "implementation_branch": result.implementation_branch,
            "worktree_path": result.worktree_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Asynchronous Harness Spawning
def _run_execution_in_background(repo_name: str, issue_number: int, active_gateway: Any) -> None:
    service = HarnessExecutionService(issues=active_gateway)
    try:
        service.execute_run(repo_name=repo_name, issue_number=issue_number, config=config)
    except Exception as exc:
        print(f"Background execution failed for #{issue_number}: {exc}")
    finally:
        try:
            ReconciliationService(issues=active_gateway).reconcile()
        except Exception:
            pass

@app.post("/api/issues/{issue_number}/execute")
def execute_issue(issue_number: int, background_tasks: BackgroundTasks, repo: str | None = None) -> dict[str, Any]:
    repo_cfg = get_repo_config(repo)
    active_gateway = issues_gateway or GitHubIssueGateway(cwd=repo_cfg.repo_path)
    
    # Pre-execution quick checks
    worktree_path = Path(repo_cfg.worktree_root) / f"issue-{issue_number}"
    if not worktree_path.exists():
        raise HTTPException(status_code=400, detail="Worktree path does not exist. Re-claim the issue.")
        
    background_tasks.add_task(_run_execution_in_background, repo_cfg.name, issue_number, active_gateway)
    return {"status": "started", "message": "Harness execution running in background."}

# 5. Branch Integration
@app.post("/api/issues/{issue_number}/integrate")
def integrate_issue(issue_number: int, repo: str | None = None) -> dict[str, Any]:
    repo_cfg = get_repo_config(repo)
    active_gateway = issues_gateway or GitHubIssueGateway(cwd=repo_cfg.repo_path)
    service = IntegrationService(issues=active_gateway, workspace=IntegrationWorkspaceGateway())
    try:
        result = service.integrate_issue(
            repo_path=str(repo_cfg.repo_path),
            worktree_root=str(repo_cfg.worktree_root),
            issue_number=issue_number,
        )
        if not result.succeeded:
            raise HTTPException(status_code=400, detail=result.failure_message)
        return {
            "status": "success",
            "implementation_branch": result.implementation_branch,
            "prd_branch": result.prd_branch
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 2. High-End UI/UX Refinement (`dashboard/src/App.tsx`)

#### A. Glassmorphism Visual Tokens (`App.css` or `index.css`)
Moving away from solid dark tones toward a modern tech aesthetic:
```css
.glass-panel {
  background: rgba(12, 12, 14, 0.65);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  border-radius: 8px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.glass-panel:hover {
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow: 0 12px 40px 0 rgba(0, 255, 128, 0.03);
}

.terminal-scroll::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.terminal-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}
```

#### B. Log Streaming Smart Scroll-Lock
This ensures logs scroll automatically **unless** the developer deliberately scrolls up to investigate a line of output.

```tsx
const terminalRef = useRef<HTMLDivElement>(null);
const [scrollLocked, setScrollLocked] = useState(true);

const handleTerminalScroll = () => {
  if (!terminalRef.current) return;
  const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
  // If user is scrolled up more than 40px from the bottom, lock scrolling
  const isNearBottom = scrollHeight - scrollTop - clientHeight < 40;
  setScrollLocked(isNearBottom);
};

useEffect(() => {
  if (terminalRef.current && scrollLocked) {
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }
}, [logTail, scrollLocked]);
```

#### C. Floating Jump-to-Bottom Indicator
If a user is scrolled up and new logs stream in, display a subtle notification:
```tsx
{!scrollLocked && (
  <button 
    onClick={() => {
      setScrollLocked(true);
      if (terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }}
    className="absolute bottom-4 right-4 bg-emerald-500 hover:bg-emerald-600 text-black font-mono text-[9px] font-bold px-2 py-1 rounded shadow animate-bounce"
  >
    ▲ NEW LOGS - CLICK TO SCROLL
  </button>
)}
```

---

## Part 2: Zero-Config Global Packaging System

To run `bersama` anywhere on your machine without copying files or authoring config sheets for every single repository:

### 1. Auto-Discovery Logic (`src/bersama/config.py`)

Enhance the load method to fallback automatically to Zero-Config mode:

```python
import subprocess
import os

def load_config(path: str | Path | None = None) -> AppConfig:
    # If no config is passed or path doesn't exist, activate Auto-Discovery
    if not path or not Path(path).exists():
        return load_auto_discovered_config()
        
    # Standard load logic...
    # ...

def load_auto_discovered_config() -> AppConfig:
    cwd = Path.cwd()
    
    # 1. Verify we are in a Git workspace
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ConfigError(
            "No bersama.yaml config found, and current directory is not a Git repository. "
            "Zero-config mode requires a Git directory."
        ) from exc

    # 2. Extract repository name
    repo_name = cwd.name
    
    # 3. Query local git refs for main branch name
    main_branch = "main"
    try:
        res = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=cwd, capture_output=True, text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            main_branch = res.stdout.strip().split("/")[-1]
    except Exception:
        # Fallback query for local HEAD
        try:
            res_local = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd, capture_output=True, text=True
            )
            if res_local.returncode == 0:
                main_branch = res_local.stdout.strip()
        except Exception:
            pass

    # 4. Standard sandbox directory outside the repository (Clean workspace principle)
    home_dir = Path.home()
    worktree_root = home_dir / ".bersama" / "worktrees" / repo_name

    # 5. Define a robust default agent harness
    # Falls back to a standard tdd execution or custom local script
    default_harness = "global-codex"
    harnesses = {
        "global-codex": HarnessConfig(
            name="global-codex",
            command="codex",
            args_template=(
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "$tdd solve issue #{issue_number} on github and commit once complete"
            )
        )
    }

    repos = {
        repo_name: RepoConfig(
            name=repo_name,
            repo_path=cwd,
            main_branch=main_branch,
            worktree_root=worktree_root,
            global_concurrency=2,
            per_prd_concurrency=1,
            default_harness=default_harness,
        )
    }

    return AppConfig(repos=repos, harnesses=harnesses)
```

---

### 2. Global CLI Setup (`pyproject.toml` integration)

Bersama has a console script entry point already declared in `pyproject.toml`:
```toml
[project.scripts]
bersama = "bersama.cli:main"
```

To install the executable globally across your system in editable mode (so local system changes apply immediately without re-installation):

```bash
# Navigate to the project root directory where pyproject.toml lives
cd /home/ungku/programming/bersama

# Install via pip editable mode for current user
pip install --user -e .
```

#### Verification:
Once complete, open a clean terminal tab and query the executable path:
```bash
which bersama
# Output: /home/ungku/.local/bin/bersama (or similar system binary directory)
```

---

### 3. Usage Example: Orchestrating an Unconfigured Project

Now, you can navigate to **any** target repository (e.g., `my-cool-project`), which contains no together configs or TOML rules, and orchestrate it cleanly:

```bash
# 1. Change directories to the target
cd /home/ungku/programming/my-cool-project

# 2. Run the orchestrator in zero-config auto-discovery mode
bersama run --auto

# 3. Spin up the control cockpit interface for this folder
bersama dashboard --auto
```
The global system will automatically instantiate sandboxed worktrees under `~/.bersama/worktrees/my-cool-project/`, keeping the target codebase clean.
