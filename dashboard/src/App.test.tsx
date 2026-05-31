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
    readiness_checks: [],
    implementation_issue_state: {
      items: [],
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

    expect(screen.getByText(/Scheduling Readiness/i)).toBeInTheDocument()

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
})
