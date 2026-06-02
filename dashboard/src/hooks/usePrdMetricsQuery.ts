import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export function usePrdMetricsQuery(repo: string, prdNumber: number | null) {
  return useQuery({
    queryKey: ['prd-metrics', repo, prdNumber],
    queryFn: async () => {
      const res = await fetch(
        `${API_BASE}/api/metrics/${encodeURIComponent(repo)}/prd/${prdNumber}`
      )
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: !!repo && prdNumber !== null,
  })
}
