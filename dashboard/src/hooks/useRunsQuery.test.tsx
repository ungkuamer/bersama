import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useRunsQuery } from './useRunsQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockRuns = [
  {
    issue_number: 8,
    status: 'running',
    prd_branch: 'prd/1-parent-prd',
    implementation_branch: 'impl/1/8-child-impl',
    started_at: '2026-05-29T16:00:00Z'
  }
]

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useRunsQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo is selected', () => {
    const { result } = renderHook(() => useRunsQuery(''), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches runs when repo is selected', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockRuns),
    })

    const { result } = renderHook(() => useRunsQuery('demo'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockRuns)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/runs?repo=demo')
    )
  })

  it('refetches every 5 seconds only when fallback polling is enabled', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockRuns),
    })

    const { unmount } = renderHook(() => useRunsQuery('demo', true), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })

    expect(mockFetch).toHaveBeenCalledTimes(2)
    unmount()
  })
})
