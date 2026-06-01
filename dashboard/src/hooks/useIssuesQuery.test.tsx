import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useIssuesQuery } from './useIssuesQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockIssues = [
  {
    number: 1,
    title: 'Test PRD',
    labels: ['prd'],
    state: 'open',
    kind: 'prd'
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

describe('useIssuesQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo is selected', () => {
    const { result } = renderHook(() => useIssuesQuery(''), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches issues when repo is selected', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockIssues),
    })

    const { result } = renderHook(() => useIssuesQuery('demo'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockIssues)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/issues?repo=demo')
    )
  })

  it('refetches every 5 seconds only when fallback polling is enabled', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockIssues),
    })

    const { unmount } = renderHook(
      ({ fallback }) => useIssuesQuery('demo', fallback),
      {
        wrapper: createWrapper(),
        initialProps: { fallback: true },
      },
    )

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

  it('does not poll when fallback polling is disabled', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockIssues),
    })

    const { unmount } = renderHook(() => useIssuesQuery('demo', false), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetch).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    unmount()
  })
})
