import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useReposQuery } from './useReposQuery'
import type { ReactNode } from 'react'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const mockRepos = [
  {
    name: 'demo',
    repo_path: '/path/to/demo',
    main_branch: 'main',
    worktree_root: '/path/to/demo/worktrees',
    global_concurrency: 2,
    per_prd_concurrency: 1,
    default_harness: 'local-agent'
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

describe('useReposQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('fetches repos from /api/repos', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockRepos),
    })

    const { result } = renderHook(() => useReposQuery(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(mockRepos)
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/repos'))
  })
})
