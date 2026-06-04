import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export interface QualityGateSummary {
  status: 'passed' | 'failed' | 'error' | 'not run' | 'invalid' | 'unavailable'
  message?: string
}

export function useQualityGateSummaryQuery(repo: string, issueNumber: number | null) {
  return useQuery<QualityGateSummary>({
    queryKey: ['quality-gate-summary', repo, issueNumber],
    queryFn: async () => {
      const res = await fetch(
        `${API_BASE}/api/repos/${encodeURIComponent(repo)}/implementation-issues/${issueNumber}/quality-gate`
      )
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: !!repo && issueNumber !== null,
  })
}
