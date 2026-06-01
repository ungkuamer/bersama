import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

// Mock global fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  )
}

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
        blocked_by: [10, 12],
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

const mockIntegrationIssues = [
  {
    number: 4,
    title: "Integration PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/4-integration-prd",
    children: [
      {
        number: 11,
        title: "Succeeded implementation issue",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 4,
        implementation_branch: "impl/4/11-succeeded",
        blocked_by: [],
        active_blockers: [],
        status: "succeeded",
        finished_at: "2026-05-29T18:00:00Z"
      },
      {
        number: 12,
        title: "Running implementation issue",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 4,
        implementation_branch: "impl/4/12-running",
        blocked_by: [],
        active_blockers: [],
        status: "running",
        started_at: "2026-05-29T18:05:00Z"
      }
    ]
  }
];

const mockClaimIssues = [
  {
    number: 5,
    title: "Claim PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/5-claim-prd",
    children: [
      {
        number: 21,
        title: "Ready claim candidate",
        labels: ["implementation", "ready-for-agent"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 5,
        implementation_branch: undefined,
        blocked_by: [],
        active_blockers: [],
        status: "ready"
      },
      {
        number: 22,
        title: "Blocked claim candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 5,
        implementation_branch: undefined,
        blocked_by: [21],
        active_blockers: [21],
        status: "blocked"
      }
    ]
  }
];

const mockClaimedAfterActionIssues = [
  {
    number: 5,
    title: "Claim PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/5-claim-prd",
    children: [
      {
        number: 21,
        title: "Ready claim candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 5,
        implementation_branch: "impl/5/21-ready-claim-candidate",
        blocked_by: [],
        active_blockers: [],
        status: "claimed",
        agent_run_id: "run-edited-21",
        claimed_at: "2026-05-29T21:20:00Z"
      }
    ]
  }
];

const mockStartIssues = [
  {
    number: 6,
    title: "Start PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/6-start-prd",
    children: [
      {
        number: 31,
        title: "Claimed start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: "impl/6/31-claimed-start-candidate",
        agent_run_id: "run-claimed-31",
        claimed_at: "2026-05-29T21:40:00Z",
        blocked_by: [],
        active_blockers: [],
        status: "claimed"
      },
      {
        number: 32,
        title: "Unclaimed start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: undefined,
        blocked_by: [],
        active_blockers: [],
        status: "unready"
      },
      {
        number: 33,
        title: "Running start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: "impl/6/33-running-start-candidate",
        blocked_by: [],
        active_blockers: [],
        status: "running",
        started_at: "2026-05-29T21:41:00Z"
      },
      {
        number: 34,
        title: "Failed start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: "impl/6/34-failed-start-candidate",
        blocked_by: [],
        active_blockers: [],
        status: "failed",
        started_at: "2026-05-29T21:42:00Z"
      },
      {
        number: 35,
        title: "Blocked start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: undefined,
        blocked_by: [31],
        active_blockers: [31],
        status: "blocked"
      },
      {
        number: 36,
        title: "Ready start candidate",
        labels: ["implementation", "ready-for-agent"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: undefined,
        blocked_by: [],
        active_blockers: [],
        status: "ready"
      },
      {
        number: 37,
        title: "Succeeded start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: "impl/6/37-succeeded-start-candidate",
        blocked_by: [],
        active_blockers: [],
        status: "succeeded",
        finished_at: "2026-05-29T21:43:00Z"
      }
    ]
  }
];

const mockStartedAfterActionIssues = [
  {
    number: 6,
    title: "Start PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/6-start-prd",
    children: [
      {
        number: 31,
        title: "Claimed start candidate",
        labels: ["implementation"],
        state: "open",
        kind: "implementation",
        parent_prd_number: 6,
        implementation_branch: "impl/6/31-claimed-start-candidate",
        agent_run_id: "run-claimed-31",
        claimed_at: "2026-05-29T21:40:00Z",
        blocked_by: [],
        active_blockers: [],
        status: "running",
        started_at: "2026-05-29T21:50:00Z"
      }
    ]
  }
];

const mockStartedRun = [
  {
    issue_number: 31,
    status: "running",
    prd_branch: "prd/6-start-prd",
    implementation_branch: "impl/6/31-claimed-start-candidate",
    started_at: "2026-05-29T21:50:00Z"
  }
];

const mockStartedLogs = {
  issue_number: 31,
  log_path: "/path/to/demo/worktrees/issue-31/harness.log",
  lines_returned: 1,
  content: "agent run accepted"
};

const mockIntegratedAfterActionIssues = [
  {
    number: 4,
    title: "Integration PRD Title",
    labels: ["prd"],
    state: "open",
    kind: "prd",
    prd_branch: "prd/4-integration-prd",
    children: [
      {
        number: 11,
        title: "Succeeded implementation issue",
        labels: ["implementation"],
        state: "closed",
        kind: "implementation",
        parent_prd_number: 4,
        implementation_branch: "impl/4/11-succeeded",
        blocked_by: [],
        active_blockers: [],
        status: "succeeded",
        finished_at: "2026-05-29T18:00:00Z"
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

const updatedMockLogs = {
  issue_number: 8,
  log_path: "/path/to/demo/worktrees/issue-8/harness.log",
  lines_returned: 3,
  content: "harness execution started...\nbuilding assets...\nnew output arrived"
};

const setLogScrollMetrics = (
  element: HTMLElement,
  metrics: { scrollTop: number; clientHeight: number; scrollHeight: number }
) => {
  Object.defineProperty(element, 'scrollTop', {
    value: metrics.scrollTop,
    writable: true,
    configurable: true
  });
  Object.defineProperty(element, 'clientHeight', {
    value: metrics.clientHeight,
    configurable: true
  });
  Object.defineProperty(element, 'scrollHeight', {
    value: metrics.scrollHeight,
    configurable: true
  });
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
    renderWithProviders(<App />);
    
    // Check loading indicator or titles
    expect(screen.getByText(/Bersama/i)).toBeInTheDocument();
    expect(screen.getByText(/Bersama OS/i)).toBeInTheDocument();
    
    // Wait for repos and data to load
    await waitFor(() => {
      expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
      expect(screen.getByText(/demo/i)).toBeInTheDocument();
    });

    // Check statistics numbers
    expect(screen.getByText(/Active Runs/i)).toBeInTheDocument();
  });

  it('displays PRDs and implementation issues correctly', async () => {
    renderWithProviders(<App />);
    
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

  it('shows open and resolved Blocking Dependencies in a compact dependency rail', async () => {
    renderWithProviders(<App />);

    await screen.findByText(/Child implementation issue/i);

    const rail = screen.getByRole('group', {
      name: /Blocking Dependency rail for Implementation Issue #8/i
    });

    expect(rail).toHaveTextContent(/Blocking Dependency/i);
    expect(screen.getByLabelText(/Open Blocking Dependency #10/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Resolved Blocking Dependency #12/i)).toBeInTheDocument();
  });

  it('displays recent agent runs and handles log loading', async () => {
    renderWithProviders(<App />);
    
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
      expect(screen.getAllByText(/harness\.log/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/harness execution started/i)).toBeInTheDocument();
      expect(screen.getByText(/building assets/i)).toBeInTheDocument();
    });
  });

  it('auto-scrolls the Agent Run log when new output arrives near the bottom', async () => {
    let logRequests = 0;
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
        logRequests += 1;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(logRequests >= 2 ? updatedMockLogs : mockLogs)
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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));

    const logViewer = await screen.findByRole('log', { name: /Issue #8 harness log tail/i });
    await screen.findByText(/building assets/i);
    setLogScrollMetrics(logViewer, { scrollTop: 500, clientHeight: 100, scrollHeight: 620 });

    fireEvent.change(screen.getByLabelText(/Log tail limit/i), { target: { value: '50' } });

    await screen.findByText(/new output arrived/i);
    expect(logViewer.scrollTop).toBe(logViewer.scrollHeight);
    expect(screen.queryByRole('button', { name: /Jump to latest log output/i })).not.toBeInTheDocument();
  });

  it('keeps the Agent Run log scroll position when new output arrives after the user scrolled up', async () => {
    let logRequests = 0;
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
        logRequests += 1;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(logRequests >= 2 ? updatedMockLogs : mockLogs)
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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));

    const logViewer = await screen.findByRole('log', { name: /Issue #8 harness log tail/i });
    await screen.findByText(/building assets/i);
    setLogScrollMetrics(logViewer, { scrollTop: 120, clientHeight: 100, scrollHeight: 620 });
    fireEvent.scroll(logViewer);

    fireEvent.change(screen.getByLabelText(/Log tail limit/i), { target: { value: '50' } });

    await screen.findByText(/new output arrived/i);
    expect(logViewer.scrollTop).toBe(120);
    expect(screen.getByRole('button', { name: /Jump to latest log output/i })).toBeInTheDocument();
  });

  it('resumes Agent Run log auto-scroll after jumping to the latest output', async () => {
    let logRequests = 0;
    const finalMockLogs = {
      ...updatedMockLogs,
      lines_returned: 4,
      content: `${updatedMockLogs.content}\nfinal output`
    };
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
        logRequests += 1;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(logRequests >= 3 ? finalMockLogs : logRequests >= 2 ? updatedMockLogs : mockLogs)
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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));

    const logViewer = await screen.findByRole('log', { name: /Issue #8 harness log tail/i });
    await screen.findByText(/building assets/i);
    setLogScrollMetrics(logViewer, { scrollTop: 120, clientHeight: 100, scrollHeight: 620 });
    fireEvent.scroll(logViewer);

    fireEvent.change(screen.getByLabelText(/Log tail limit/i), { target: { value: '50' } });
    const jumpButton = await screen.findByRole('button', { name: /Jump to latest log output/i });
    fireEvent.click(jumpButton);

    expect(logViewer.scrollTop).toBe(logViewer.scrollHeight);
    expect(screen.queryByRole('button', { name: /Jump to latest log output/i })).not.toBeInTheDocument();

    setLogScrollMetrics(logViewer, { scrollTop: 500, clientHeight: 100, scrollHeight: 650 });
    fireEvent.change(screen.getByLabelText(/Log tail limit/i), { target: { value: '100' } });

    await screen.findByText(/final output/i);
    expect(logViewer.scrollTop).toBe(logViewer.scrollHeight);
  });

  it('exports the currently loaded Agent Run log tail with an issue-specific tail filename', async () => {
    const createObjectURL = vi.fn<(object: Blob | MediaSource) => string>(() => 'blob:tail-export');
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.fn();
    const createdAnchors: HTMLAnchorElement[] = [];
    const originalCreateElement = document.createElement.bind(document);

    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true
    });
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      const element = originalCreateElement(tagName);
      if (tagName.toLowerCase() === 'a') {
        element.click = anchorClick;
        createdAnchors.push(element as HTMLAnchorElement);
      }
      return element;
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));
    await screen.findByText(/building assets/i);

    fireEvent.click(screen.getByRole('button', { name: /Export loaded tail for Implementation Issue #8/i }));

    const exportedBlob = createObjectURL.mock.calls[0][0] as Blob;
    await expect(exportedBlob.text()).resolves.toBe(mockLogs.content);

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:tail-export');
    expect(createdAnchors[0].download).toBe('implementation-issue-8-log-tail.txt');
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

    renderWithProviders(<App />);

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

    renderWithProviders(<App />);

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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Prepare PRD #2/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Issue is not a PRD Issue.");
    expect(screen.queryByText(/Connection issue/i)).not.toBeInTheDocument();
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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Prepare PRD #2/i }));

    await waitFor(() => {
      expect(screen.getByText(/Connection issue/i)).toBeInTheDocument();
      expect(screen.getByText(/Failed to connect to backend: Failed to fetch/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows Integrate only for succeeded Implementation Issues', async () => {
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
          json: () => Promise.resolve(mockIntegrationIssues)
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

    renderWithProviders(<App />);

    await screen.findByText('Succeeded implementation issue');
    expect(screen.getByRole('button', { name: /Integrate #11/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Integrate #12/i })).not.toBeInTheDocument();
  });

  it('does not show Integrate for already integrated closed Implementation Issues', async () => {
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
          json: () => Promise.resolve(mockIntegratedAfterActionIssues)
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

    renderWithProviders(<App />);

    await screen.findByText('Succeeded implementation issue');
    expect(screen.queryByRole('button', { name: /Integrate #11/i })).not.toBeInTheDocument();
  });

  it('integrates a succeeded Implementation Issue through the repo-scoped backend route and refreshes data after success', async () => {
    let issuesRequests = 0;
    let finishIntegration: (() => void) | undefined;
    const integrationResponse = new Promise((resolve) => {
      finishIntegration = () => resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          status: "integrated",
          issue_number: 11,
          implementation_branch: "impl/4/11-succeeded",
          prd_branch: "prd/4-integration-prd"
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
            issuesRequests >= 2 ? mockIntegratedAfterActionIssues : mockIntegrationIssues
          )
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/11/integrate')) {
        expect(options?.method).toBe('POST');
        return integrationResponse;
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    const integrateButton = await screen.findByRole('button', { name: /Integrate #11/i });
    fireEvent.click(integrateButton);

    expect(await screen.findByRole('button', { name: /Integrating #11/i })).toBeDisabled();
    finishIntegration?.();

    await waitFor(() => {
      expect(screen.getByText(/Integrated Implementation Issue #11 into prd\/4-integration-prd/i)).toBeInTheDocument();
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/dashboard/repos/demo/implementation-issues/11/integrate', {
        method: 'POST'
      });
      expect(issuesRequests).toBeGreaterThanOrEqual(2);
    });
  });

  it('shows known integration failures locally on the affected Implementation Issue row', async () => {
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
          json: () => Promise.resolve(mockIntegrationIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/11/integrate')) {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ detail: "Merge conflict while updating implementation branch against PRD branch." })
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Integrate #11/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Merge conflict while updating implementation branch against PRD branch.");
    expect(screen.queryByText(/Connection issue/i)).not.toBeInTheDocument();
  });

  it('keeps integration connectivity failures in the global system fault banner', async () => {
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
          json: () => Promise.resolve(mockIntegrationIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/11/integrate')) {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Integrate #11/i }));

    await waitFor(() => {
      expect(screen.getByText(/Connection issue/i)).toBeInTheDocument();
      expect(screen.getByText(/Failed to connect to backend: Failed to fetch/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows Claim only for Ready Implementation Issues', async () => {
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
          json: () => Promise.resolve(mockClaimIssues)
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

    renderWithProviders(<App />);

    await screen.findByText('Ready claim candidate');

    expect(screen.getByRole('button', { name: /Claim #21/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Claim #22/i })).not.toBeInTheDocument();
  });

  it('opens an inline claim form with an editable generated Agent Run identifier', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1780090000123);
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
          json: () => Promise.resolve(mockClaimIssues)
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

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Claim #21/i }));

    const agentRunInput = screen.getByLabelText(/Agent Run identifier for Implementation Issue #21/i);
    expect(agentRunInput).toHaveValue('run-21-19e75a1d2fb');

    fireEvent.change(agentRunInput, { target: { value: 'run-human-readable-21' } });

    expect(agentRunInput).toHaveValue('run-human-readable-21');
  });

  it('claims a Ready Implementation Issue with the edited Agent Run identifier and refreshes data after success', async () => {
    let issuesRequests = 0;
    let finishClaim: (() => void) | undefined;
    const claimResponse = new Promise((resolve) => {
      finishClaim = () => resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          status: "claimed",
          issue_number: 21,
          agent_run_id: "run-edited-21",
          implementation_branch: "impl/5/21-ready-claim-candidate"
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
            issuesRequests >= 2 ? mockClaimedAfterActionIssues : mockClaimIssues
          )
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/21/claim')) {
        expect(options?.method).toBe('POST');
        expect(options?.headers).toEqual({ 'Content-Type': 'application/json' });
        expect(options?.body).toBe(JSON.stringify({ agent_run_id: 'run-edited-21' }));
        return claimResponse;
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Claim #21/i }));
    fireEvent.change(screen.getByLabelText(/Agent Run identifier for Implementation Issue #21/i), {
      target: { value: 'run-edited-21' }
    });
    fireEvent.click(screen.getByRole('button', { name: /Submit claim for Implementation Issue #21/i }));

    expect(await screen.findByRole('button', { name: /Claiming #21/i })).toBeDisabled();
    finishClaim?.();

    await waitFor(() => {
      expect(screen.getByText(/Claimed Implementation Issue #21 with run-edited-21/i)).toBeInTheDocument();
      expect(screen.getByText(/impl\/5\/21-ready-claim-candidate/i)).toBeInTheDocument();
      expect(issuesRequests).toBeGreaterThanOrEqual(2);
    });
  });

  it('shows known claim failures locally on the affected Implementation Issue row', async () => {
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
          json: () => Promise.resolve(mockClaimIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/21/claim')) {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ detail: "Implementation Issue is already claimed." })
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Claim #21/i }));
    fireEvent.click(screen.getByRole('button', { name: /Submit claim for Implementation Issue #21/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Implementation Issue is already claimed.");
    expect(screen.queryByText(/Connection issue/i)).not.toBeInTheDocument();
  });

  it('shows Start Agent Run only for Claimed Implementation Issues', async () => {
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
          json: () => Promise.resolve(mockStartIssues)
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

    renderWithProviders(<App />);

    await screen.findByText('Claimed start candidate');

    expect(screen.getByRole('button', { name: /Start Agent Run for Implementation Issue #31/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #32/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #33/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #34/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #35/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #36/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Start Agent Run for Implementation Issue #37/i })).not.toBeInTheDocument();
  });

  it('starts a Claimed Implementation Issue through the repo-scoped backend route, refreshes data, and selects its log view after success', async () => {
    let issuesRequests = 0;
    let runsRequests = 0;
    let finishStart: (() => void) | undefined;
    const startResponse = new Promise((resolve) => {
      finishStart = () => resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          status: "started",
          issue_number: 31,
          agent_run_id: "run-claimed-31",
          run_state_path: "/path/to/demo/worktrees/issue-31/run-state.json",
          log_path: "/path/to/demo/worktrees/issue-31/harness.log"
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
            issuesRequests >= 2 ? mockStartedAfterActionIssues : mockStartIssues
          )
        });
      }
      if (url.includes('/api/runs/31/log')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockStartedLogs)
        });
      }
      if (url.includes('/api/runs')) {
        runsRequests += 1;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(
            runsRequests >= 2 ? mockStartedRun : []
          )
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/31/start')) {
        expect(options?.method).toBe('POST');
        return startResponse;
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    const startButton = await screen.findByRole('button', {
      name: /Start Agent Run for Implementation Issue #31/i
    });
    fireEvent.click(startButton);

    expect(await screen.findByRole('button', { name: /Starting Agent Run for Implementation Issue #31/i })).toBeDisabled();
    finishStart?.();

    await waitFor(() => {
      expect(screen.getByText(/Started Agent Run run-claimed-31 for Implementation Issue #31/i)).toBeInTheDocument();
      expect(screen.getByText(/agent run accepted/i)).toBeInTheDocument();
      expect(issuesRequests).toBeGreaterThanOrEqual(2);
      expect(runsRequests).toBeGreaterThanOrEqual(2);
    });

    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/dashboard/repos/demo/implementation-issues/31/start', {
      method: 'POST'
    });
  });

  it('shows known start failures locally on the affected Implementation Issue row', async () => {
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
          json: () => Promise.resolve(mockStartIssues)
        });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      if (url.endsWith('/dashboard/repos/demo/implementation-issues/31/start')) {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ detail: "Implementation Issue worktree does not exist: /worktrees/demo/issue-31" })
        });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', {
      name: /Start Agent Run for Implementation Issue #31/i
    }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Implementation Issue worktree does not exist: /worktrees/demo/issue-31");
    expect(screen.queryByText(/Connection issue/i)).not.toBeInTheDocument();
  });

  it('renders log search input in terminal console header when a run is selected', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
      }
      if (url.includes('/api/runs/8/log')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockLogs) });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));
    await screen.findByText(/harness execution started/i);

    expect(screen.getByPlaceholderText(/Search log/i)).toBeInTheDocument();
  });

  it('highlights matching search terms with mark elements in the log viewport', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
      }
      if (url.includes('/api/runs/8/log')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockLogs) });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));
    await screen.findByText(/harness execution started/i);

    const searchInput = screen.getByPlaceholderText(/Search log/i);
    fireEvent.change(searchInput, { target: { value: 'harness' } });

    const marks = document.querySelectorAll('mark');
    expect(marks.length).toBeGreaterThan(0);
    expect(marks[0]).toHaveTextContent('harness');
  });

  it('highlights multiple search matches in the same line with separate mark elements', async () => {
    const multiMatchLogs = {
      issue_number: 8,
      log_path: '/path/to/demo/worktrees/issue-8/harness.log',
      lines_returned: 1,
      content: 'error error error in the log stream'
    };

    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
      }
      if (url.includes('/api/runs/8/log')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(multiMatchLogs) });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));
    await screen.findByText(/error error error/);

    const searchInput = screen.getByPlaceholderText(/Search log/i);
    fireEvent.change(searchInput, { target: { value: 'error' } });

    const marks = document.querySelectorAll('mark');
    expect(marks.length).toBe(3);
    for (const mark of marks) {
      expect(mark).toHaveTextContent('error');
    }
  });

  describe('Side Drawer Inspector', () => {
    it('opens the side drawer when clicking an implementation issue title', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Find and click the implementation issue in the list (not in drawer)
      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      // Drawer should be visible
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getAllByText(/Child implementation issue/i).length).toBeGreaterThan(1);
      });
    });

    it('closes the drawer when clicking the close button', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Open drawer
      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      // Verify drawer is open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Close via close button
      const closeButton = screen.getByRole('button', { name: /Close/i });
      fireEvent.click(closeButton);

      // Drawer should be gone
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });

    it('opens the side drawer when clicking a PRD card title', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Find and click the PRD title (the h3 element, not the drawer title)
      const prdTitles = await screen.findAllByText(/Parent PRD Title/i);
      const prdTitle = prdTitles.find(el => el.tagName === 'H3')!;
      fireEvent.click(prdTitle);

      // Drawer should be visible
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(screen.getAllByText(/PRD #1/i).length).toBeGreaterThan(1);
      });
    });

    it('closes the drawer when clicking the scrim overlay', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Open drawer
      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      // Verify drawer is open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Click the overlay (scrim) — Radix uses onPointerDown
      const overlay = document.querySelector('[data-slot="sheet-overlay"]');
      expect(overlay).toBeInTheDocument();
      fireEvent.pointerDown(overlay!);

      // Drawer should be gone
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });

    it('contains Overview, Readiness Timeline, and Operations tabs', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Open drawer
      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Three tabs should be visible
      const overviewTabs = screen.getAllByText(/Overview/i);
      expect(overviewTabs.length).toBeGreaterThan(0);
      const timelineTabs = screen.getAllByText(/Readiness Timeline/i);
      expect(timelineTabs.length).toBeGreaterThan(0);
      const operationsTabs = screen.getAllByText(/Operations/i);
      expect(operationsTabs.length).toBeGreaterThan(0);
    });

    it('shows metadata in the Overview tab', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

      const dialog = screen.getByRole('dialog');
      // Switch to Overview tab (since it defaults to Operations in Operator view)
      const overviewTab = within(dialog).getByRole('button', { name: /Overview/i });
      fireEvent.click(overviewTab);

      // Overview tab should show state and kind metadata
      expect(screen.getByText(/Status & Metadata/i)).toBeInTheDocument();
      expect(screen.getByText(/Blocking Dependencies/i)).toBeInTheDocument();
    });

    it('shows Operations tab with action controls for eligible issues', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

      // Click Operations tab
      const operationsTabs = screen.getAllByText(/Operations/i);
      const operationsTab = operationsTabs.find(el => el.tagName === 'BUTTON')!;
      fireEvent.click(operationsTab);

      // Should show action controls section
      await waitFor(() => {
        expect(screen.getByText(/Action Controls/i)).toBeInTheDocument();
      });

      // Should show git parameters
      expect(screen.getByText(/Git Parameters/i)).toBeInTheDocument();
    });

    it('Claim action in Operations tab opens the claim form', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockClaimIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Click ready claim candidate in the list
      const issueLinks = await screen.findAllByText(/Ready claim candidate/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

      const dialog = screen.getByRole('dialog');

      // Switch to Operations tab within the drawer
      const operationsTabs = within(dialog).getAllByText(/Operations/i);
      const operationsTab = operationsTabs.find(el => el.tagName === 'BUTTON')!;
      fireEvent.click(operationsTab);

      // Click Claim button within the drawer
      await waitFor(() => {
        expect(within(dialog).getByText(/Claim #21/i)).toBeInTheDocument();
      });

      const claimButton = within(dialog).getByText(/Claim #21/i).closest('button')!;
      fireEvent.click(claimButton);

      // Should show claim form with Agent Run ID field
      await waitFor(() => {
        expect(within(dialog).getByText(/Agent Run ID/i)).toBeInTheDocument();
      });
    });

    it('shows shimmer skeletons during loading states', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          // Keep loading state
          return new Promise(() => {});
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Should show shimmer skeletons while data is loading
      await waitFor(() => {
        const shimmers = document.querySelectorAll('.animate-shimmer');
        expect(shimmers.length).toBeGreaterThan(0);
      });
    });
  });

  it('shows a pulsing stream indicator when log polling is active and a run is selected', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
      }
      if (url.includes('/api/issues')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
      }
      if (url.includes('/api/runs/8/log')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockLogs) });
      }
      if (url.includes('/api/runs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
      }
      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
    });

    renderWithProviders(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /View Log/i }));
    await screen.findByText(/harness execution started/i);

    // The stream indicator should be visible when polling is active
    expect(screen.getByTitle(/Streaming active/i)).toBeInTheDocument();
  });

  describe('Tab Switcher Layout & Navigation', () => {
    const mockReadinessData = {
      repo: {
        name: "demo",
        path: "/repos/demo",
        main_branch: "main",
        worktree_root: "/worktrees/demo"
      },
      snapshot: {
        observed_at: "2026-05-31T20:00:00Z",
        config_provenance: {
          source: "app-config",
          default_harness: {
            name: "local",
            timeout_seconds: 3600
          }
        },
        harness_summary: {
          default_harness: "local",
          timeout_seconds: 3600
        },
        readiness_checks: {
          critical_failures: [
            {
              message: "Required repository labels are missing.",
              remediation: "Add the required labels in GitHub before running scheduling.",
              details: {
                code: "missing-required-labels",
                missing_labels: ["claimed", "ready-for-agent"]
              }
            }
          ],
          warnings: [
            {
              message: "Working tree has local changes.",
              remediation: "Review local changes before running scheduling.",
              details: {
                code: "working-tree-dirty"
              }
            }
          ]
        },
        implementation_issue_state: {
          items: [
            {
              issue_number: 10,
              title: "Implement feature A",
              status: "ready",
              blocked_by: [],
              active_blockers: [],
              timeline: {}
            }
          ],
          groups: [
            {
              parent_prd: {
                issue_number: 2,
                title: "PRD: Auth flows",
                prepared: true
              },
              items: [
                {
                  issue_number: 10,
                  title: "Implement feature A",
                  status: "ready",
                  blocked_by: [],
                  active_blockers: [],
                  timeline: {}
                }
              ]
            }
          ],
          summary: {
            ready: 1,
            blocked: 0,
            claimed: 0,
            running: 0,
            failed: 0,
            succeeded: 0,
            other: 0
          },
          agent_run_capacity: {
            used: 2,
            total: 4
          }
        }
      }
    };

    it('renders navigation tabs and switches between read-only readiness and interactive operator view', async () => {
      // Mock the new readiness endpoint along with default fetches
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRuns) });
        }
        if (url.includes('/api/scheduling-readiness/demo')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockReadinessData) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Wait for app load
      await waitFor(() => {
        expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Lifecycle/i })).toBeInTheDocument();
      });

      // Under test environment, Operator Console is active initially to keep existing tests intact
      expect(screen.getByText(/Product Roadmap & Implementation Lifecycle/i)).toBeInTheDocument();
      expect(screen.queryByText(/Repository Summary/i)).not.toBeInTheDocument();

      // Click on Dashboard tab
      const readinessTab = screen.getByText(/Dashboard/i);
      fireEvent.click(readinessTab);

      // Verify Scheduling Readiness panel elements are loaded
      await waitFor(() => {
        expect(screen.getByText(/Repository Summary/i)).toBeInTheDocument();
      });

      // 1. Observed Timestamps & Unmasked configuration provenance paths
      expect(screen.getByText(/\/repos\/demo/i)).toBeInTheDocument();
      expect(screen.getByText(/^main$/)).toBeInTheDocument();

      // 2. Default harness variables unmasked
      expect(screen.getByText(/^local$/i)).toBeInTheDocument();
      expect(screen.getByText(/3600s/i)).toBeInTheDocument();

      // 3. Active capacity usage limits (used / total)
      expect(screen.getByText((_, node) => node?.textContent === '2/4')).toBeInTheDocument();

      // 4. Critical Readiness Failures & Warnings with diagnostics + remediation
      expect(screen.getByText(/Required repository labels are missing./i)).toBeInTheDocument();
      expect(screen.getByText(/Add the required labels in GitHub before running scheduling./i)).toBeInTheDocument();
      expect(screen.getByText(/CODE: missing-required-labels/i)).toBeInTheDocument();

      expect(screen.getByText(/Working tree has local changes./i)).toBeInTheDocument();
      expect(screen.getByText(/Review local changes before running scheduling./i)).toBeInTheDocument();
      expect(screen.getByText(/CODE: working-tree-dirty/i)).toBeInTheDocument();

      // 5. Open Implementation Issues grouped by Parent PRD
      expect(screen.getByText(/PRD #2/i)).toBeInTheDocument();
      expect(screen.getByText(/PRD: Auth flows/i)).toBeInTheDocument();
      expect(screen.getAllByText(/#10/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Implement feature A/i)).toBeInTheDocument();

      // 6. Contains no action buttons (Prepare, Claim, Start, Integrate) or inputs inside panel
      const textMatches = (text: string) => screen.queryAllByText(new RegExp(`^${text}$`, 'i'));
      expect(textMatches('Prepare')).toHaveLength(0);
      expect(textMatches('Claim')).toHaveLength(0);
      expect(textMatches('Start')).toHaveLength(0);
      expect(textMatches('Integrate')).toHaveLength(0);

      // Switch back to Lifecycle
      const operatorTab = screen.getByRole('button', { name: /Lifecycle/i });
      fireEvent.click(operatorTab);

      // Product Roadmap is visible again, and Scheduling Readiness panel is unmounted
      await waitFor(() => {
        expect(screen.getByText(/Product Roadmap & Implementation Lifecycle/i)).toBeInTheDocument();
      });
      expect(screen.queryByText(/Repository Summary/i)).not.toBeInTheDocument();
    });

    it('opens side drawer in readOnly mode when clicking an issue in Scheduling Readiness view', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url.includes('/api/scheduling-readiness/demo')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockReadinessData) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Go to Scheduling Readiness
      const readinessTab = screen.getByText(/Dashboard/i);
      fireEvent.click(readinessTab);

      // Verify page is rendered
      expect(await screen.findByText(/Repository Summary/i)).toBeInTheDocument();

      // Click on "Implement feature A" issue
      const issueLink = screen.getByText(/Implement feature A/i);
      fireEvent.click(issueLink);

      // Drawer should open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Verify that the Overview and Readiness Timeline tabs are visible
      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Readiness Timeline')).toBeInTheDocument();

      // Operations tab should be completely hidden (readOnly)
      expect(screen.queryByText('Operations')).not.toBeInTheDocument();
    });

    it('opens side drawer in operations mode by default when clicking an issue in Operator Console view', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.endsWith('/api/repos')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockRepos) });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockIssues) });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      renderWithProviders(<App />);

      // Operator Console is active initially
      expect(await screen.findByText(/Product Roadmap & Implementation Lifecycle/i)).toBeInTheDocument();

      // Find and click the implementation issue in the list
      const issueLinks = await screen.findAllByText(/Child implementation issue/i);
      const issueLink = issueLinks.find(el => el.tagName === 'SPAN')!;
      fireEvent.click(issueLink);

      // Drawer should open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      const dialog = screen.getByRole('dialog');

      // Verify that the Operations tab button is visible
      const operationsButton = within(dialog).getByRole('button', { name: /Operations/i });
      expect(operationsButton).toBeInTheDocument();

      // Since we expect it to be active by default, it should have the active tab styling class
      expect(operationsButton).toHaveClass('border-primary');

      // Overview button should not be active
      const overviewButton = within(dialog).getByRole('button', { name: /Overview/i });
      expect(overviewButton).not.toHaveClass('border-primary');

      // Operations tab content (Git Parameters) should be rendered
      expect(within(dialog).getByText('Git Parameters')).toBeInTheDocument();
    });
  });

  describe('Theme Toggler', () => {
    it('toggles theme between dark and light modes and persists to localStorage', async () => {
      mockFetch.mockImplementation((url: string) => {
        if (url.includes('/api/repos')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockRepos),
          });
        }
        if (url.includes('/api/issues')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockIssues),
          });
        }
        if (url.includes('/api/runs')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([]),
          });
        }
        return Promise.reject(new Error(`Unhandled mock fetch for ${url}`));
      });

      localStorage.clear();

      renderWithProviders(<App />);

      expect(document.documentElement.classList.contains('dark')).toBe(false);

      const themeBtn = await screen.findByTitle('Switch to dark mode');
      expect(themeBtn).toBeInTheDocument();

      fireEvent.click(themeBtn);

      expect(document.documentElement.classList.contains('dark')).toBe(true);
      expect(localStorage.getItem('theme')).toBe('dark');

      fireEvent.click(themeBtn);
      expect(document.documentElement.classList.contains('dark')).toBe(false);
      expect(localStorage.getItem('theme')).toBe('light');
    });
  });
});
