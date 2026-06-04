import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export interface QualityGateCheck {
  id: string
  name: string
  type?: string | null
  status: string
  advisory?: boolean
  message?: string | null
}

export interface QualityGateSummary {
  status: 'passed' | 'failed' | 'error' | 'not run' | 'not_run' | 'invalid' | 'unavailable'
  message?: string
  checks?: QualityGateCheck[]
}

export function useQualityGateSummaryQuery(
  repo: string,
  issueNumber: number | null,
  options?: {
    enablePollingFallback?: boolean
    drawerOpen?: boolean
  }
) {
  const isEnabled = !!repo && issueNumber !== null && (options?.drawerOpen ?? true)
  return useQuery<QualityGateSummary>({
    queryKey: ['quality-gate-summary', repo, issueNumber],
    queryFn: async () => {
      const res = await fetch(
        `${API_BASE}/api/repos/${encodeURIComponent(repo)}/implementation-issues/${issueNumber}/quality-gate`
      )
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: isEnabled,
    refetchInterval: isEnabled && options?.enablePollingFallback ? 5_000 : false,
    refetchIntervalInBackground: isEnabled && (options?.enablePollingFallback ?? false),
  })
}

