import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { usePrdMetricsQuery } from './usePrdMetricsQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockPrdMetrics = {
  issue_number: 123,
  diagnostics: [] as Array<{ code: string; severity: string; message: string }>,
  metrics_available: true,
  implementation_issue_count: 3,
  child_status_counts: { succeeded: 2, ready: 1 },
  total_run_count: 5,
  successful_run_count: 4,
  integrated_run_count: 2,
  runs_with_telemetry: 4,
  runs_without_telemetry: 1,
  input_tokens: 15000,
  output_tokens: 7500,
  cache_read_tokens: 1800,
  cache_write_tokens: 900,
  total_tokens: 25200,
  model_cost: 0.135,
  tool_call_count: 108,
  tool_error_count: 6,
  avg_time_to_first_token_ms: 480.0,
  avg_latency_ms: 1200.0,
  avg_output_tokens_per_sec: 88.5,
}

const mockPrdMetricsUnavailable = {
  issue_number: 124,
  diagnostics: [
    {
      code: 'missing_association',
      severity: 'warning',
      message: 'No Agent Run associations found.',
    },
  ],
  metrics_available: false,
  implementation_issue_count: 1,
  child_status_counts: { claimed: 1 },
  total_run_count: 1,
  successful_run_count: 0,
  integrated_run_count: 0,
  runs_with_telemetry: 0,
  runs_without_telemetry: 1,
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

describe('usePrdMetricsQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo or prd number is provided', () => {
    const { result } = renderHook(() => usePrdMetricsQuery('', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('does not fetch when prd number is null', () => {
    const { result } = renderHook(() => usePrdMetricsQuery('demo', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches PRD metrics when repo and prd number are provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockPrdMetrics),
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 123),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockPrdMetrics)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/metrics/demo/prd/123')
    )
  })

  it('returns aggregated PRD metrics with child counts', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockPrdMetrics),
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 123),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(true)
    expect(result.current.data?.implementation_issue_count).toBe(3)
    expect(result.current.data?.total_run_count).toBe(5)
    expect(result.current.data?.successful_run_count).toBe(4)
    expect(result.current.data?.runs_with_telemetry).toBe(4)
    expect(result.current.data?.runs_without_telemetry).toBe(1)
    expect(result.current.data?.child_status_counts).toEqual({ succeeded: 2, ready: 1 })
  })

  it('returns aggregated model usage metrics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockPrdMetrics),
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 123),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.input_tokens).toBe(15000)
    expect(result.current.data?.output_tokens).toBe(7500)
    expect(result.current.data?.total_tokens).toBe(25200)
    expect(result.current.data?.model_cost).toBe(0.135)
  })

  it('returns averaged responsiveness metrics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockPrdMetrics),
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 123),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.avg_time_to_first_token_ms).toBe(480.0)
    expect(result.current.data?.avg_latency_ms).toBe(1200.0)
    expect(result.current.data?.avg_output_tokens_per_sec).toBe(88.5)
  })

  it('returns metrics_available false when no telemetry available', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockPrdMetricsUnavailable),
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 124),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(false)
    expect(result.current.data?.diagnostics).toHaveLength(1)
    expect(result.current.data?.diagnostics?.[0].code).toBe('missing_association')
    expect(result.current.data?.runs_with_telemetry).toBe(0)
    expect(result.current.data?.runs_without_telemetry).toBe(1)
  })

  it('handles fetch errors gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
    })

    const { result } = renderHook(
      () => usePrdMetricsQuery('demo', 999),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
