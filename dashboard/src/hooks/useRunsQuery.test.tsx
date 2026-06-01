import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
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
})
