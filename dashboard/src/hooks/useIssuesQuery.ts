import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export function useIssuesQuery(repo: string, enablePollingFallback = false) {
  return useQuery({
    queryKey: ['issues', repo],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/issues?repo=${encodeURIComponent(repo)}`)
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: !!repo,
    refetchInterval: enablePollingFallback ? 5_000 : false,
    refetchIntervalInBackground: enablePollingFallback,
  })
}
