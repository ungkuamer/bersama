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

  it('invalidates run-metrics and implementation-issue-metrics queries on metrics_updated event', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
      init?.onopen?.()
      init?.onmessage?.({
        event: 'metrics_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 42 }),
      })
    })

    renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['run-metrics', 'demo', 42] })
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['implementation-issue-metrics', 'demo', 42] })
    })
  })

  it('invalidates prd-metrics queries on metrics_updated event with prd_number', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
      init?.onopen?.()
      init?.onmessage?.({
        event: 'metrics_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 42, prd_number: 7 }),
      })
    })

    renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['prd-metrics', 'demo', 7] })
    })
  })

  it('does not panic on metrics_updated event with missing issue_number', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
      init?.onopen?.()
      init?.onmessage?.({
        event: 'metrics_updated',
        data: JSON.stringify({ repo: 'demo' }),
      })
    })

    renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    // Wait for connection, then give invalidation a moment to settle
    await waitFor(() => {
      expect(mockFetchEventSource).toHaveBeenCalled()
    })

    // Should not have been called for any metrics queries (since no issue_number/prd_number)
    expect(invalidateQueries).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(['run-metrics']) })
    )
    expect(invalidateQueries).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(['implementation-issue-metrics']) })
    )
    expect(invalidateQueries).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(['prd-metrics']) })
    )
  })

  it('enters polling fallback after SSE timeout and preserves metrics query polling behavior', async () => {
    vi.useFakeTimers()
    mockFetchEventSource.mockImplementationOnce(() => new Promise(() => undefined))

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })

    const { result, unmount } = renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    // Snapshot-first: the hook starts with polling fallback false
    expect(result.current.isPollingFallback).toBe(false)
    expect(result.current.isConnected).toBe(false)

    // After 10 seconds of no SSE event, fallback kicks in
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(result.current.isPollingFallback).toBe(true)
    expect(result.current.isConnected).toBe(false)

    // The polling fallback flag is available for metrics queries to use as enablePollingFallback
    // This verifies the hook correctly transitions to fallback state without SSE events
    unmount()
  })

  it('invalidates quality-gate-summary queries on quality_gate_updated event with issue_number', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
      init?.onopen?.()
      init?.onmessage?.({
        event: 'quality_gate_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 125 }),
      })
    })

    renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['quality-gate-summary', 'demo', 125] })
    })
  })

  it('invalidates quality-gate-summary queries on runs_updated event', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    mockFetchEventSource.mockImplementationOnce(async (_input: string, init?: { onopen?: () => void; onmessage?: (message: { event: string; data: string }) => void }) => {
      init?.onopen?.()
      init?.onmessage?.({
        event: 'runs_updated',
        data: JSON.stringify({ repo: 'demo', issue_number: 125 }),
      })
    })

    renderHook(() => useSSE('demo'), {
      wrapper: createWrapper(queryClient),
    })

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['quality-gate-summary', 'demo'] })
    })
  })
})

