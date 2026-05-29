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
        blocked_by: [],
        status: "unready"
      }
    ]
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
    expect(screen.getAllByText(/UNREADY/i).length).toBeGreaterThan(0);
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
});
