import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
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
  })

  it('connects on mount, invalidates issue and run queries from stream events, and aborts on unmount', async () => {
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

    expect(result.current).toEqual({
      event: 'runs_updated',
      data: { repo: 'demo', issue_number: 18 },
    })

    expect(abortSignal?.aborted).toBe(false)
    unmount()
    expect(abortSignal?.aborted).toBe(true)
  })
})
