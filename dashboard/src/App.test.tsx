import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockRepos = [
  {
    name: 'demo',
    repo_path: '/path/to/demo',
    main_branch: 'main',
    worktree_root: '/path/to/demo/worktrees',
    global_concurrency: 2,
    per_prd_concurrency: 1,
    default_harness: 'local-agent',
  },
]

const mockSchedulingReadinessSnapshot = {
  repo: {
    name: 'demo',
    path: '/path/to/demo',
    main_branch: 'main',
    worktree_root: '/path/to/demo/worktrees',
  },
  snapshot: {
    observed_at: '2026-05-31T18:30:00Z',
    config_provenance: {
      source: 'app-config',
      default_harness: {
        name: 'local-agent',
        timeout_seconds: 900,
      },
    },
    harness_summary: {
      default_harness: 'local-agent',
      timeout_seconds: 900,
    },
    readiness_checks: {
      critical_failures: [],
      warnings: [],
    },
    implementation_issue_state: {
      items: [],
      groups: [],
      agent_run_capacity: {
        used: 0,
        total: 2,
      },
      summary: {
        ready: 0,
        blocked: 0,
        claimed: 0,
        running: 0,
        failed: 0,
        succeeded: 0,
        other: 0,
      },
    },
  },
}

describe('Scheduling Readiness landing view', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos),
        })
      }

      if (url.includes('/api/scheduling-readiness/demo')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockSchedulingReadinessSnapshot),
        })
      }

      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`))
    })
  })

  it('renders Scheduling Readiness as the landing view for the selected repo', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Scheduling Readiness' })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('/path/to/demo')).toBeInTheDocument()
    })

    expect(screen.getByDisplayValue('demo')).toBeInTheDocument()
    expect(screen.getByText('/path/to/demo/worktrees')).toBeInTheDocument()
    expect(screen.getByText('local-agent')).toBeInTheDocument()
    expect(screen.getByText('900s')).toBeInTheDocument()
    expect(screen.getByText(/No readiness checks yet/i)).toBeInTheDocument()
    expect(screen.getByText(/No implementation issues observed yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Claim/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Start/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Integrate/i })).not.toBeInTheDocument()
  })

  it('loads the landing view without lifecycle mutations or auto-refresh polling', async () => {
    render(<App />)

    await waitFor(() => {
      const requestedUrls = mockFetch.mock.calls.map(([url]) => String(url))
      expect(requestedUrls.some((url) => url.includes('/api/scheduling-readiness/demo'))).toBe(true)
    })

    const requestedUrls = mockFetch.mock.calls.map(([url]) => String(url))
    expect(requestedUrls.some((url) => url.includes('/api/repos'))).toBe(true)
    expect(requestedUrls.some((url) => url.includes('/api/scheduling-readiness/demo'))).toBe(true)
    expect(requestedUrls.some((url) => url.includes('/dashboard/repos/demo/reconcile'))).toBe(false)
    expect(requestedUrls.some((url) => url.includes('/api/issues'))).toBe(false)
    expect(requestedUrls.some((url) => url.includes('/api/runs'))).toBe(false)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('renders critical readiness failures separately from warnings with human-readable remediation', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos),
        })
      }

      if (url.includes('/api/scheduling-readiness/demo')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockSchedulingReadinessSnapshot,
              snapshot: {
                ...mockSchedulingReadinessSnapshot.snapshot,
                readiness_checks: {
                  critical_failures: [
                    {
                      message: 'Required repository labels are missing.',
                      remediation: 'Add the required labels in GitHub before running scheduling.',
                      details: {
                        code: 'missing-required-labels',
                        missing_labels: ['prd', 'claimed'],
                      },
                    },
                  ],
                  warnings: [
                    {
                      message: 'Working tree has local changes.',
                      remediation: 'Review local changes before running scheduling.',
                      details: {
                        code: 'working-tree-dirty',
                      },
                    },
                  ],
                },
              },
            }),
        })
      }

      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/Critical readiness failures/i)).toBeInTheDocument()
    })

    expect(screen.getByText('Required repository labels are missing.')).toBeInTheDocument()
    expect(
      screen.getByText('Add the required labels in GitHub before running scheduling.')
    ).toBeInTheDocument()
    expect(screen.getByText(/Readiness warnings/i)).toBeInTheDocument()
    expect(screen.getByText('Working tree has local changes.')).toBeInTheDocument()
    expect(screen.getByText('Review local changes before running scheduling.')).toBeInTheDocument()
    expect(screen.queryByText(/missing-required-labels/i)).not.toBeInTheDocument()
  })

  it('renders PRD-grouped implementation issue state and agent run capacity', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos),
        })
      }

      if (url.includes('/api/scheduling-readiness/demo')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockSchedulingReadinessSnapshot,
              snapshot: {
                ...mockSchedulingReadinessSnapshot.snapshot,
                implementation_issue_state: {
                  items: [
                    { issue_number: 12, title: 'Ready issue', status: 'ready' },
                    { issue_number: 14, title: 'Running issue', status: 'running' },
                    { issue_number: 17, title: 'Needs info issue', status: 'unready' },
                  ],
                  groups: [
                    {
                      parent_prd: {
                        issue_number: 10,
                        title: 'Prepared PRD',
                        prepared: true,
                      },
                      items: [
                        {
                          issue_number: 12,
                          title: 'Ready issue',
                          status: 'ready',
                          blocked_by: [],
                          active_blockers: [],
                        },
                        {
                          issue_number: 14,
                          title: 'Running issue',
                          status: 'running',
                          blocked_by: [12],
                          active_blockers: [],
                        },
                      ],
                    },
                    {
                      parent_prd: {
                        issue_number: 11,
                        title: 'Unprepared PRD',
                        prepared: false,
                      },
                      items: [
                        {
                          issue_number: 17,
                          title: 'Needs info issue',
                          status: 'unready',
                          blocked_by: [14],
                          active_blockers: [14],
                        },
                      ],
                    },
                  ],
                  agent_run_capacity: {
                    used: 1,
                    total: 2,
                  },
                  summary: {
                    ready: 1,
                    blocked: 0,
                    claimed: 0,
                    running: 1,
                    failed: 0,
                    succeeded: 0,
                    other: 1,
                  },
                },
              },
            }),
        })
      }

      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Ready issue')).toBeInTheDocument()
    })

    expect(screen.getByText(/Agent Run Capacity 1 \/ 2/i)).toBeInTheDocument()
    expect(screen.getAllByText('Prepared PRD')).toHaveLength(2)
    expect(screen.getAllByText(/Unprepared PRD/)).toHaveLength(2)
    expect(screen.getByText('Ready issue')).toBeInTheDocument()
    expect(screen.getByText('Running issue')).toBeInTheDocument()
    expect(screen.getByText('Needs info issue')).toBeInTheDocument()
  })

  it('renders the Dependency Pipeline in Scheduling Readiness without Work Queue wording', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/api/repos')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRepos),
        })
      }

      if (url.includes('/api/scheduling-readiness/demo')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockSchedulingReadinessSnapshot,
              snapshot: {
                ...mockSchedulingReadinessSnapshot.snapshot,
                implementation_issue_state: {
                  items: [
                    { issue_number: 12, title: 'Failed issue', status: 'failed', parent_prd_number: 10 },
                    { issue_number: 13, title: 'Needs info issue', status: 'unready', parent_prd_number: 10 },
                    { issue_number: 14, title: 'Blocked issue', status: 'blocked', parent_prd_number: 10 },
                    { issue_number: 15, title: 'Ready issue', status: 'ready', parent_prd_number: 10 },
                    { issue_number: 16, title: 'Claimed issue', status: 'claimed', parent_prd_number: 10 },
                    { issue_number: 17, title: 'Running issue', status: 'running', parent_prd_number: 10 },
                    { issue_number: 18, title: 'Succeeded issue', status: 'succeeded', parent_prd_number: 10 },
                  ],
                  groups: [
                    {
                      parent_prd: {
                        issue_number: 10,
                        title: 'Prepared PRD',
                        prepared: true,
                      },
                      items: [
                        {
                          issue_number: 12,
                          title: 'Failed issue',
                          status: 'failed',
                          blocked_by: [],
                          active_blockers: [],
                        },
                        {
                          issue_number: 13,
                          title: 'Needs info issue',
                          status: 'unready',
                          blocked_by: [12],
                          active_blockers: [],
                        },
                        {
                          issue_number: 14,
                          title: 'Blocked issue',
                          status: 'blocked',
                          blocked_by: [13],
                          active_blockers: [13],
                        },
                        {
                          issue_number: 15,
                          title: 'Ready issue',
                          status: 'ready',
                          blocked_by: [14],
                          active_blockers: [14],
                        },
                        {
                          issue_number: 16,
                          title: 'Claimed issue',
                          status: 'claimed',
                          blocked_by: [15],
                          active_blockers: [],
                        },
                        {
                          issue_number: 17,
                          title: 'Running issue',
                          status: 'running',
                          blocked_by: [16],
                          active_blockers: [],
                        },
                        {
                          issue_number: 18,
                          title: 'Succeeded issue',
                          status: 'succeeded',
                          blocked_by: [17],
                          active_blockers: [],
                        },
                      ],
                    },
                  ],
                  agent_run_capacity: {
                    used: 1,
                    total: 2,
                  },
                  summary: {
                    ready: 1,
                    blocked: 1,
                    claimed: 1,
                    running: 1,
                    failed: 1,
                    succeeded: 1,
                    other: 1,
                  },
                },
              },
            }),
        })
      }

      return Promise.reject(new Error(`Unhandled mock fetch for ${url}`))
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByLabelText(/Dependency pipeline visualization/i)).toBeInTheDocument()
    })

    expect(screen.getByRole('heading', { name: 'Dependency Pipeline' })).toBeInTheDocument()
    expect(screen.getByText(/Implementation Issue State dependency visual/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Dependency pipeline visualization/i)).toBeInTheDocument()
    expect(screen.getAllByText('#12').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#13').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#14').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#15').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#16').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#17').length).toBeGreaterThan(0)
    expect(screen.getAllByText('#18').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Work Queue/i)).not.toBeInTheDocument()
  })
})
