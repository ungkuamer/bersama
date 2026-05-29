import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import App from './App'

// Mock global fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

const mockRepos = [
  {
    name: "demo",
    repo_path: "/path/to/demo",
    main_branch: "main",
    worktree_root: "/path/to/demo/worktrees",
    global_concurrency: 2,
    per_prd_concurrency: 1,
    default_harness: "local-agent"
  }
];

const mockIssues = [
  {
    number: 1,
    title: "Parent PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/1-parent-prd",
    children: [
      {
        number: 8,
        title: "Child implementation issue",
        labels: ["implementation", "ready-for-agent"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 1,
        implementation_branch: "impl/1/8-child-impl",
        blocked_by: [10],
        active_blockers: [10],
        status: "running",
        started_at: "2026-05-29T16:00:00Z"
      },
      {
        number: 10,
        title: "Blocker implementation issue",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 1,
        implementation_branch: "impl/1/10-blocker-impl",
        agent_run_id: "run-456",
        claimed_at: "2026-05-29T17:00:00Z",
        blocked_by: [],
        status: "claimed"
      }
    ]
  }
];

const mockUnpreparedIssues = [
  {
    number: 2,
    title: "Unprepared PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: null,
    children: []
  },
  {
    number: 3,
    title: "Prepared PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/3-prepared-prd",
    children: []
  }
];

const mockPreparedAfterActionIssues = [
  {
    number: 2,
    title: "Unprepared PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/2-unprepared-prd-title",
    children: []
  }
];

const mockRuns = [
  {
    issue_number: 8,
    status: "running",
    prd_branch: "prd/1-parent-prd",
    implementation_branch: "impl/1/8-child-impl",
    started_at: "2026-05-29T16:00:00Z"
  }
];

const mockLogs = {
  issue_number: 8,
  log_path: "/path/to/demo/worktrees/issue-8/harness.log",
  lines_returned: 2,
  content: "harness execution started...\nbuilding assets..."
};

describe('Bersama Dashboard Frontend', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    
    // Default mock setup for fetches
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos)
        });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockIssues)
        });
      }
      if (url.includes('/api/runs/8/log')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockLogs)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRuns)
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });
  });

  it('renders dashboard with primary branding and structure', async () => {
    render(<App />);
    
    // Check loading indicator or titles
    expect(screen.getByText(/Bersama/i)).toBeInTheDocument();
    expect(screen.getByText(/Agent Orchestration/i)).toBeInTheDocument();
    
    // Wait for repos and data to load
    await waitFor(() => {
      expect(screen.getByText(/REPO:/i)).toBeInTheDocument();
      expect(screen.getByText(/demo/i)).toBeInTheDocument();
    });

    // Check statistics numbers
    expect(screen.getByText(/ACTIVE RUNS:/i)).toBeInTheDocument();
  });

  it('displays PRDs and implementation issues correctly', async () => {
    render(<App />);
    
    // Wait for data load
    await waitFor(() => {
      expect(screen.getByText(/Parent PRD Title/i)).toBeInTheDocument();
    });

    // Expanded state shows children
    expect(screen.getByText(/Child implementation issue/i)).toBeInTheDocument();
    expect(screen.getByText(/Blocker implementation issue/i)).toBeInTheDocument();
    expect(screen.getAllByText(/RUNNING/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CLAIMED/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/run-456/i)).toBeInTheDocument();
  });

  it('displays recent agent runs and handles log loading', async () => {
    render(<App />);
    
    // Wait for runs to render
    await waitFor(() => {
      expect(screen.getByText(/Recent Agent Runs/i)).toBeInTheDocument();
      expect(screen.getByText(/ISSUE #8/i)).toBeInTheDocument();
    });

    // Check console is originally empty
    expect(screen.getByText(/Console is offline/i)).toBeInTheDocument();

    // Click "View Log" button on the implementation issue
    const viewLogBtn = screen.getByRole('button', { name: /View Log/i });
    fireEvent.click(viewLogBtn);

    // Should load the terminal and present logs
    await waitFor(() => {
      expect(screen.getByText(/Terminal Console/i)).toBeInTheDocument();
      expect(screen.getByText(/harness execution started/i)).toBeInTheDocument();
      expect(screen.getByText(/building assets/i)).toBeInTheDocument();
    });
  });

  it('shows Prepare PRD only for open unprepared PRD Issues', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos)
        });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockUnpreparedIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Unprepared PRD Title')).toBeInTheDocument();
      expect(screen.getByText('Prepared PRD Title')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Prepare PRD #2/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Prepare PRD #3/i })).not.toBeInTheDocument();
  });

  it('prepares a PRD Issue through the repo-scoped backend route and refreshes data after success', async () => {
    let issuesRequests = 0;
    let finishPrepare: (() => void) | undefined;
    const prepareResponse = new Promise((resolve) => {
      finishPrepare = () => resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          status: "prepared",
          issue_number: 2,
          prd_branch: "prd/2-unprepared-prd-title"
        })
      });
    });

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos)
        });
      }
      if (url.includes('/api/issues')) {
        issuesRequests += 1;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(
            issuesRequests >= 2 ? mockPreparedAfterActionIssues : mockUnpreparedIssues
          )
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/prd-issues/2/prepare')) {
        expect(options?.method).toBe('POST');
        return prepareResponse;
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    render(<App />);

    const prepareButton = await screen.findByRole('button', { name: /Prepare PRD #2/i });
    fireEvent.click(prepareButton);

    expect(await screen.findByRole('button', { name: /Preparing PRD #2/i })).toBeDisabled();
    finishPrepare?.();

    await waitFor(() => {
      expect(screen.getByText(/Prepared PRD #2/i)).toBeInTheDocument();
      expect(screen.getByText(/BRANCH: prd\/2-unprepared-prd-title/i)).toBeInTheDocument();
    });

    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/dashboard/repos/demo/prd-issues/2/prepare', {
      method: 'POST'
    });
    expect(issuesRequests).toBeGreaterThanOrEqual(2);
  });

  it('shows known PRD preparation failures locally on the affected PRD Issue', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos)
        });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockUnpreparedIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/prd-issues/2/prepare')) {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ detail: "Issue is not a PRD Issue." })
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Prepare PRD #2/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Issue is not a PRD Issue.");
    expect(screen.queryByText(/SYSTEM FAULT/i)).not.toBeInTheDocument();
  });

  it('keeps backend connectivity failures in the global system fault banner', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos)
        });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockUnpreparedIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/prd-issues/2/prepare')) {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Prepare PRD #2/i }));

    await waitFor(() => {
      expect(screen.getByText(/SYSTEM FAULT:/i)).toBeInTheDocument();
      expect(screen.getByText(/Failed to connect to backend: Failed to fetch/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
