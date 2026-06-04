import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useQualityGateSummaryQuery } from './useQualityGateSummaryQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

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

describe('useQualityGateSummaryQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo or issue number is provided', () => {
    const { result } = renderHook(() => useQualityGateSummaryQuery('', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches quality gate summary when repo and issue number are provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: 'passed', message: 'All checks passed' }),
    })

    const { result } = renderHook(
      () => useQualityGateSummaryQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/repos/demo/implementation-issues/125/quality-gate')
    )
    expect(result.current.data).toEqual({ status: 'passed', message: 'All checks passed' })
  })

  it('handles API error status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    })

    const { result } = renderHook(
      () => useQualityGateSummaryQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(Error)
    expect(result.current.error?.message).toContain('HTTP error 500')
  })

  it('refetches every 5 seconds only when fallback polling is enabled and drawer is open', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'passed' }),
    })

    const { unmount } = renderHook(
      () => useQualityGateSummaryQuery('demo', 125, { enablePollingFallback: true, drawerOpen: true }),
      { wrapper: createWrapper() }
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

  it('does not fetch or poll when drawer is closed', async () => {
    vi.useFakeTimers()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'passed' }),
    })

    const { unmount } = renderHook(
      () => useQualityGateSummaryQuery('demo', 125, { enablePollingFallback: true, drawerOpen: false }),
      { wrapper: createWrapper() }
    )

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetch).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })

    expect(mockFetch).not.toHaveBeenCalled()
    unmount()
  })
})

