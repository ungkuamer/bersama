import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useRunLogQuery } from './useRunLogQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockLogTail = {
  issue_number: 8,
  log_path: '/path/to/demo/worktrees/issue-8/harness.log',
  lines_returned: 2,
  content: 'harness execution started...\nbuilding assets...'
}

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

describe('useRunLogQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when issueNumber is null', () => {
    const { result } = renderHook(() => useRunLogQuery('demo', null, 100), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches run log when issueNumber is provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockLogTail),
    })

    const { result } = renderHook(() => useRunLogQuery('demo', 8, 100), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockLogTail)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/runs/8/log?limit=100&repo=demo')
    )
  })

  it('handles 404 gracefully by returning synthetic not found object', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
    })

    const { result } = renderHook(() => useRunLogQuery('demo', 99, 100), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      issue_number: 99,
      log_path: 'System Path',
      lines_returned: 0,
      content: 'Log file not found yet. The agent run might be starting up...'
    })
  })

  it('refetches every 2 seconds only when fallback polling is enabled', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockLogTail),
    })

    const { unmount } = renderHook(() => useRunLogQuery('demo', 8, 100, true), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })

    expect(mockFetch).toHaveBeenCalledTimes(2)
    unmount()
  })
})
