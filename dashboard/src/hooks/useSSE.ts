import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const API_BASE = import.meta.env.DEV ? `http://${window.location.hostname}:8000` : ''

export interface SSEMessage {
  event: string
  data: Record<string, unknown>
}

export interface SSEState {
  latestMessage: SSEMessage | null
  isConnected: boolean
  isPollingFallback: boolean
}

const BACKOFF_DELAYS_MS = [1_000, 2_000, 4_000, 8_000]
const MAX_BACKOFF_DELAY_MS = 30_000
const FALLBACK_TIMEOUT_MS = 10_000
const INITIAL_SSE_STATE: SSEState = {
  latestMessage: null,
  isConnected: false,
  isPollingFallback: false,
}

export function useSSE(repo: string) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<SSEState>(INITIAL_SSE_STATE)

  useEffect(() => {
    if (!repo) {
      return
    }

    let isDisposed = false
    let retryAttempt = 0
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined
    let hasEverConnected = false
    let hasMessageForCurrentAttempt = false
    let controller: AbortController | undefined

    const clearFallbackTimer = () => {
      if (fallbackTimer) {
        clearTimeout(fallbackTimer)
        fallbackTimer = undefined
      }
    }

    const startFallbackTimer = () => {
      clearFallbackTimer()
      hasMessageForCurrentAttempt = false
      fallbackTimer = setTimeout(() => {
        if (isDisposed || hasMessageForCurrentAttempt) return
        setState(prev => ({
          ...prev,
          isConnected: false,
          isPollingFallback: true,
        }))
      }, FALLBACK_TIMEOUT_MS)
    }

    const invalidateAllRepoData = async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['issues', repo] }),
        queryClient.invalidateQueries({ queryKey: ['runs', repo] }),
      ])
    }

    const reconnectDelay = () => {
      if (retryAttempt < BACKOFF_DELAYS_MS.length) {
        return BACKOFF_DELAYS_MS[retryAttempt]
      }
      return MAX_BACKOFF_DELAY_MS
    }

    const scheduleReconnect = () => {
      if (isDisposed) return
      const delay = reconnectDelay()
      retryAttempt += 1
      reconnectTimer = setTimeout(() => {
        void connect()
      }, delay)
    }

    const connect = async () => {
      controller = new AbortController()
      startFallbackTimer()

      try {
        await fetchEventSource(`${API_BASE}/api/events?repo=${encodeURIComponent(repo)}`, {
          signal: controller.signal,
          onopen: async () => {
            if (isDisposed) return
            setState(prev => ({
              ...prev,
              isConnected: true,
              isPollingFallback: false,
            }))
            if (hasEverConnected) {
              await invalidateAllRepoData()
            }
            hasEverConnected = true
          },
          async onmessage(message) {
            const parsedData = JSON.parse(message.data) as Record<string, unknown>
            hasMessageForCurrentAttempt = true
            clearFallbackTimer()
            retryAttempt = 0
            setState({
              latestMessage: { event: message.event, data: parsedData },
              isConnected: true,
              isPollingFallback: false,
            })

            if (message.event === 'issues_updated') {
              await queryClient.invalidateQueries({ queryKey: ['issues', repo] })
            }

            if (message.event === 'runs_updated') {
              await invalidateAllRepoData()
            }

            if (message.event === 'metrics_updated') {
              const issueNumber = typeof parsedData.issue_number === 'number' ? parsedData.issue_number : null
              const prdNumber = typeof parsedData.prd_number === 'number' ? parsedData.prd_number : null

              if (issueNumber !== null) {
                await Promise.all([
                  queryClient.invalidateQueries({ queryKey: ['run-metrics', repo, issueNumber] }),
                  queryClient.invalidateQueries({ queryKey: ['implementation-issue-metrics', repo, issueNumber] }),
                ])
              }

              if (prdNumber !== null) {
                await queryClient.invalidateQueries({ queryKey: ['prd-metrics', repo, prdNumber] })
              }
            }
          },
          onerror(error) {
            throw error
          },
        })
      } catch {
        if (isDisposed || controller.signal.aborted) return
        clearFallbackTimer()
        setState(prev => ({
          ...prev,
          isConnected: false,
        }))
        scheduleReconnect()
      }
    }

    void connect()

    return () => {
      isDisposed = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      clearFallbackTimer()
      controller?.abort()
    }
  }, [queryClient, repo])

  return repo ? state : INITIAL_SSE_STATE
}
