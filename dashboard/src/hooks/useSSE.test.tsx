import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useSSE } from './useSSE'

const { mockFetchEventSource } = vi.hoisted(() => ({
  mockFetchEventSource: vi.fn(),
}))

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: mockFetchEventSource,
}))

const createWrapper = (queryClient: QueryClient) => {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('connects on mount, reports live status, invalidates issue and run queries from stream events, and aborts on unmount', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    let abortSignal: AbortSignal | undefined

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { signal?: AbortSignal; onmessage?: (message: { event: string; data: string }) => void }) => {
      abortSignal = init?.signal
      init?.onmessage?.({
        event: 'issues_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 18 }),
      })
      init?.onmessage?.({
        event: 'runs_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 18 }),
      })
    })

    const { result, unmount } = renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalledWith(
        expect.stringContaining('/api/events?repo=demo'),
        expect.objectContaining({
          signal: expect.any(AbortSignal),
        }),
      )
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['issues', 'demo'] })
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['runs', 'demo'] })
    })

    expect(result.current.latestMessage).toEqual({
      event: 'runs_updated',
      data: { repo: 'demo', issue_number: 18 },
    })
    expect(result.current.isConnected).toBe(true)
    expect(result.current.isPollingFallback).toBe(false)

    expect(abortSignal?.aborted).toBe(false)
    unmount()
    expect(abortSignal?.aborted).toBe(true)
  })

  it('falls back to polling when no SSE event arrives within 10 seconds', async () => {
    vi.useFakeTimers()
    mockFetchEventSource.mockImplementationOnce(() => new Promise(() => undefined))

    const { result, unmount } = renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(new QueryClient()),
    })

    expect(result.current.isPollingFallback).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(result.current.isConnected).toBe(false)
    expect(result.current.isPollingFallback).toBe(true)
    unmount()
  })

  it('reconnects with exponential backoff and refreshes missed issue and run data', async () => {
    vi.useFakeTimers()
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource
      .mockImplementationOnce(async (_input: string, init?: { onopen?: () => void }) => {
        init?.onopen?.()
        throw new Error('network down')
      })
      .mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
        init?.onopen?.()
        init?.onmessage?.({
          event: 'issues_updated',
          data: JSON.stringify({ repo: 'demo', issue_number: 18 }),
        })
      })

    const { unmount } = renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetchEventSource).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(999)
    })
    expect(mockFetchEventSource).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mockFetchEventSource).toHaveBeenCalledTimes(2)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['issues', 'demo'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['runs', 'demo'] })
    unmount()
  })
})
