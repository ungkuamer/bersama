import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export function useRunsQuery(repo: string) {
  return useQuery({
    queryKey: ['runs', repo],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/runs?repo=${encodeURIComponent(repo)}`)
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json()
    },
    enabled: !!repo,
  })
}
