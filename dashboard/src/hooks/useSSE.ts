import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export interface SSEMessage {
  event: string
  data: Record<string, unknown>
}

export function useSSE(repo: string) {
  const queryClient = useQueryClient()
  const [latestMessage, setLatestMessage] = useState<SSEMessage | null>(null)

  useEffect(() => {
    if (!repo) {
      setLatestMessage(null)
      return
    }

    const controller = new AbortController()

    void fetchEventSource(`${API_BASE}/api/events?repo=${encodeURIComponent(repo)}`, {
      signal: controller.signal,
      async onmessage(message) {
        const parsedData = JSON.parse(message.data) as Record<string, unknown>
        setLatestMessage({ event: message.event, data: parsedData })

        if (message.event === 'issues_updated') {
          await queryClient.invalidateQueries({ queryKey: ['issues', repo] })
        }

        if (message.event === 'runs_updated') {
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['runs', repo] }),
            queryClient.invalidateQueries({ queryKey: ['issues', repo] }),
          ])
        }
      },
    }).catch(() => {
      // Library default reconnection behavior is sufficient here.
    })

    return () => {
      controller.abort()
    }
  }, [queryClient, repo])

  return latestMessage
}
