import { QueryClient } from '@tanstack/react-query'

const queryStaleTime = (queryKey: readonly unknown[]) => {
  const scope = queryKey[0]
  if (scope === 'repos') return 60000
  if (scope === 'issues' || scope === 'runs') return 5000
  return 0
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 2,
      staleTime: (query) => queryStaleTime(query.queryKey),
    },
  },
})
