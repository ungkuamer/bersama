import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useImplementationIssueMetricsQuery } from './useImplementationIssueMetricsQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockImplementationIssueMetrics = {
  issue_number: 125,
  diagnostics: [] as Array<{ code: string; severity: string; message: string }>,
  metrics_available: true,
  run_count: 3,
  successful_run_count: 2,
  runs_with_telemetry: 2,
  runs_without_telemetry: 1,
  failure_count: 1,
  latest_run_status: 'failed',
  input_tokens: 5000,
  output_tokens: 2500,
  cache_read_tokens: 600,
  cache_write_tokens: 300,
  total_tokens: 8400,
  model_cost: 0.045,
  tool_call_count: 36,
  tool_error_count: 2,
  avg_time_to_first_token_ms: 500.0,
  avg_latency_ms: 1250.0,
  avg_output_tokens_per_sec: 82.5,
}

const mockImplementationIssueMetricsUnavailable = {
  issue_number: 126,
  diagnostics: [
    {
      code: 'missing_association',
      severity: 'warning',
      message: 'No Agent Run associations found for Implementation Issue #126.',
    },
  ],
  metrics_available: false,
  run_count: 0,
  successful_run_count: 0,
  runs_with_telemetry: 0,
  runs_without_telemetry: 0,
  failure_count: 0,
  latest_run_status: null,
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

describe('useImplementationIssueMetricsQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo or issue number is provided', () => {
    const { result } = renderHook(() => useImplementationIssueMetricsQuery('', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('does not fetch when issue number is null', () => {
    const { result } = renderHook(() => useImplementationIssueMetricsQuery('demo', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches implementation issue metrics when repo and issue number are provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockImplementationIssueMetrics),
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockImplementationIssueMetrics)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/metrics/demo/implementation-issues/125')
    )
  })

  it('returns aggregated metrics with attempt count', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockImplementationIssueMetrics),
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(true)
    expect(result.current.data?.run_count).toBe(3)
    expect(result.current.data?.successful_run_count).toBe(2)
    expect(result.current.data?.failure_count).toBe(1)
    expect(result.current.data?.runs_with_telemetry).toBe(2)
    expect(result.current.data?.runs_without_telemetry).toBe(1)
    expect(result.current.data?.latest_run_status).toBe('failed')
  })

  it('returns aggregated model usage metrics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockImplementationIssueMetrics),
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.input_tokens).toBe(5000)
    expect(result.current.data?.output_tokens).toBe(2500)
    expect(result.current.data?.total_tokens).toBe(8400)
    expect(result.current.data?.model_cost).toBe(0.045)
    expect(result.current.data?.tool_call_count).toBe(36)
    expect(result.current.data?.tool_error_count).toBe(2)
  })

  it('returns averaged responsiveness metrics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockImplementationIssueMetrics),
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 125),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.avg_time_to_first_token_ms).toBe(500.0)
    expect(result.current.data?.avg_latency_ms).toBe(1250.0)
    expect(result.current.data?.avg_output_tokens_per_sec).toBe(82.5)
  })

  it('returns metrics_available false when no telemetry available', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockImplementationIssueMetricsUnavailable),
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 126),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(false)
    expect(result.current.data?.diagnostics).toHaveLength(1)
    expect(result.current.data?.diagnostics?.[0].code).toBe('missing_association')
    expect(result.current.data?.run_count).toBe(0)
    expect(result.current.data?.latest_run_status).toBeNull()
  })

  it('handles fetch errors gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
    })

    const { result } = renderHook(
      () => useImplementationIssueMetricsQuery('demo', 999),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
