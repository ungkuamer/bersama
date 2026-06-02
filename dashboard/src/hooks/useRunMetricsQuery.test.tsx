import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useRunMetricsQuery } from './useRunMetricsQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockMetrics = {
  run_id: 'run-125',
  diagnostics: [] as Array<{ code: string; severity: string; message: string }>,
  metrics_available: true,
  input_tokens: 1500,
  output_tokens: 800,
  cache_read_tokens: 200,
  cache_write_tokens: 100,
  total_tokens: 2600,
  model_cost: 0.015,
  tool_call_count: 12,
  tool_error_count: 1,
  model: 'claude-sonnet-4',
  provider: 'anthropic',
  avg_time_to_first_token_ms: 450.0,
  avg_latency_ms: 1200.0,
  avg_output_tokens_per_sec: 85.5,
  latest_time_to_first_token_ms: 320.0,
  latest_latency_ms: 980.0,
  latest_output_tokens_per_sec: 92.0,
}

const mockMetricsUnavailable = {
  run_id: 'run-126',
  diagnostics: [
    {
      code: 'missing_association',
      severity: 'warning',
      message: 'No Run Telemetry Association found.',
    },
  ],
  metrics_available: false,
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

describe('useRunMetricsQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fetch when no repo or issue number is provided', () => {
    const { result } = renderHook(() => useRunMetricsQuery('', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('does not fetch when repo is empty', () => {
    const { result } = renderHook(() => useRunMetricsQuery('', 125), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('does not fetch when issue number is null', () => {
    const { result } = renderHook(() => useRunMetricsQuery('demo', null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isPending).toBe(true)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('fetches run metrics when repo and issue number are provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockMetrics),
    })

    const { result } = renderHook(() => useRunMetricsQuery('demo', 125), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockMetrics)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/metrics/demo/runs/125')
    )
  })

  it('returns metrics_available true when telemetry is present', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockMetrics),
    })

    const { result } = renderHook(() => useRunMetricsQuery('demo', 125), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(true)
    expect(result.current.data?.input_tokens).toBe(1500)
    expect(result.current.data?.output_tokens).toBe(800)
    expect(result.current.data?.total_tokens).toBe(2600)
    expect(result.current.data?.model_cost).toBe(0.015)
    expect(result.current.data?.tool_call_count).toBe(12)
    expect(result.current.data?.tool_error_count).toBe(1)
    expect(result.current.data?.model).toBe('claude-sonnet-4')
    expect(result.current.data?.provider).toBe('anthropic')
    expect(result.current.data?.avg_time_to_first_token_ms).toBe(450.0)
    expect(result.current.data?.avg_latency_ms).toBe(1200.0)
    expect(result.current.data?.avg_output_tokens_per_sec).toBe(85.5)
    expect(result.current.data?.latest_time_to_first_token_ms).toBe(320.0)
    expect(result.current.data?.latest_latency_ms).toBe(980.0)
    expect(result.current.data?.latest_output_tokens_per_sec).toBe(92.0)
  })

  it('returns metrics_available false when telemetry is unavailable', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockMetricsUnavailable),
    })

    const { result } = renderHook(() => useRunMetricsQuery('demo', 126), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.metrics_available).toBe(false)
    expect(result.current.data?.diagnostics).toHaveLength(1)
    expect(result.current.data?.diagnostics?.[0].code).toBe('missing_association')
  })

  it('handles fetch errors gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
    })

    const { result } = renderHook(() => useRunMetricsQuery('demo', 999), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('includes cache read/write tokens in fetched metrics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockMetrics),
    })

    const { result } = renderHook(() => useRunMetricsQuery('demo', 125), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.cache_read_tokens).toBe(200)
    expect(result.current.data?.cache_write_tokens).toBe(100)
  })
})
