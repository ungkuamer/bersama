import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useLogStream } from './useLogStream'
import type { LogTail } from './useRunLogQuery'
import type { SSEMessage } from './useSSE'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch as unknown as typeof fetch

const createWrapper = (queryClient: QueryClient) => {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

const baseLogTail: LogTail = {
  issue_number: 8,
  log_path: '/worktrees/demo/issue-8/harness.log',
  lines_returned: 2,
  content: 'line 1\nline 2',
}

const appendedLogEvent = {
  event: 'log_append' as const,
  data: { repo: 'demo', issue_number: 8, lines: ['line 3', 'line 4'] },
}

describe('useLogStream', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('loads the initial log tail and accumulates appended lines for the selected Implementation Issue', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(baseLogTail),
    })

    const { result } = renderHook(
      ({ latestEvent }) =>
        useLogStream({
          repo: 'demo',
          issueNumber: 8,
          limit: 10,
          latestEvent,
        }),
      {
        initialProps: {
          latestEvent: appendedLogEvent,
        },
        wrapper: createWrapper(queryClient),
      },
    )

    await waitFor(() => expect(result.current.logTail?.content).toBe('line 1\nline 2\nline 3\nline 4'))
  })

  it('resets accumulated lines when the selected Implementation Issue changes and trims to the selected limit', async () => {
    type HookProps = { issueNumber: number; latestEvent: SSEMessage | null }
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(baseLogTail),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve<LogTail>({
            issue_number: 9,
            log_path: '/worktrees/demo/issue-9/harness.log',
            lines_returned: 2,
            content: 'next 1\nnext 2',
          }),
      })

    const { result, rerender } = renderHook<ReturnType<typeof useLogStream>, HookProps>(
      ({ issueNumber, latestEvent }: { issueNumber: number; latestEvent: SSEMessage | null }) =>
        useLogStream({
          repo: 'demo',
          issueNumber,
          limit: 3,
          latestEvent,
        }),
      {
        initialProps: {
          issueNumber: 8,
          latestEvent: appendedLogEvent,
        },
        wrapper: createWrapper(queryClient),
      },
    )

    await waitFor(() => expect(result.current.logTail?.content).toBe('line 2\nline 3\nline 4'))

    rerender({
      issueNumber: 9,
      latestEvent: null,
    })

    await waitFor(() => {
      expect(result.current.logTail?.issue_number).toBe(9)
      expect(result.current.logTail?.content).toBe('next 1\nnext 2')
    })
  })
})
