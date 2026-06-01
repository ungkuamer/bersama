import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export function useReposQuery() {
  return useQuery({
    queryKey: ['repos'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/repos`)
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      return res.json() as Promise<Array<{
        name: string
        repo_path: string
        main_branch: string
        worktree_root: string
        global_concurrency: number
        per_prd_concurrency: number
        default_harness: string
      }>>
    },
    staleTime: 60000,
  })
}
