import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
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
})
