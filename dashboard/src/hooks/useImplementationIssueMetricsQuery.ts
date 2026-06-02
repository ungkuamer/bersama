import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export function useImplementationIssueMetricsQuery(repo: string, issueNumber: number | null) {
  return useQuery({
    queryKey: ['implementation-issue-metrics', repo, issueNumber],
    queryFn: async () => {
      const res = await fetch(
        `${API_BASE}/api/metrics/${encodeURIComponent(repo)}/implementation-issues/${issueNumber}`
      )
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: !!repo && issueNumber !== null,
  })
}
