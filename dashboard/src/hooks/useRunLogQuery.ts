import { keepPreviousData, useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export interface LogTail {
  issue_number: number
  log_path: string
  lines_returned: number
  content: string
}

export function useRunLogQuery(repo: string, issueNumber: number | null, limit: number) {
  return useQuery<LogTail>({
    queryKey: ['runLog', repo, issueNumber, limit],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/runs/${issueNumber}/log?limit=${limit}&repo=${encodeURIComponent(repo)}`)
      if (!res.ok) {
        if (res.status === 404) {
          return {
            issue_number: issueNumber!,
            log_path: 'System Path',
            lines_returned: 0,
            content: 'Log file not found yet. The agent run might be starting up...'
          }
        }
        throw new Error(`HTTP error ${res.status}`)
      }
      return res.json() as Promise<LogTail>
    },
    enabled: !!repo && issueNumber !== null,
    placeholderData: keepPreviousData,
  })
}
