import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import App from './App'

// Mock global fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

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

  it('shows open and resolved Blocking Dependencies in a compact dependency rail', async () => {
    render(<App />);

    await screen.findByText(/Child implementation issue/i);

    const rail = screen.getByRole('group', {
      name: /Blocking Dependency rail for Implementation Issue #8/i
    });

    expect(rail).toHaveTextContent(/Blocking Dependency/i);
    expect(screen.getByLabelText(/Open Blocking Dependency #10/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Resolved Blocking Dependency #12/i)).toBeInTheDocument();
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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Integrate #11/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Merge conflict while updating implementation branch against PRD branch.");
    expect(screen.queryByText(/SYSTEM FAULT/i)).not.toBeInTheDocument();
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

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Integrate #11/i }));

    await waitFor(() => {
      expect(screen.getByText(/SYSTEM FAULT:/i)).toBeInTheDocument();
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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

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

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Claim #21/i }));
    fireEvent.click(screen.getByRole('button', { name: /Submit claim for Implementation Issue #21/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Implementation Issue is already claimed.");
    expect(screen.queryByText(/SYSTEM FAULT/i)).not.toBeInTheDocument();
  });
});
