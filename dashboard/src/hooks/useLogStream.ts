import { useEffect, useMemo, useRef, useState } from 'react'
import { useRunLogQuery, type LogTail } from './useRunLogQuery'
import type { SSEMessage } from './useSSE'

interface UseLogStreamOptions {
  repo: string
  issueNumber: number | null
  limit: number
  latestEvent: SSEMessage | null
}

const trimLines = (content: string, limit: number): string => {
  const lines = content.split('\n')
  if (lines.length <= limit) return content
  return lines.slice(-limit).join('\n')
}

export function useLogStream({ repo, issueNumber, limit, latestEvent }: UseLogStreamOptions) {
  const runLogQuery = useRunLogQuery(repo, issueNumber, limit)
  const [appendedLines, setAppendedLines] = useState<string[]>([])
  const previousIssueRef = useRef<number | null>(null)

  useEffect(() => {
    if (previousIssueRef.current !== issueNumber) {
      setAppendedLines([])
      previousIssueRef.current = issueNumber
    }
  }, [issueNumber])

  useEffect(() => {
    if (!latestEvent || latestEvent.event !== 'log_append') return
    if (issueNumber === null) return

    const eventIssue = typeof latestEvent.data.issue_number === 'number'
      ? latestEvent.data.issue_number
      : typeof latestEvent.data.issue === 'number'
        ? latestEvent.data.issue
        : null

    if (eventIssue !== issueNumber) return

    const linesValue = latestEvent.data.lines
    const nextLines = Array.isArray(linesValue)
      ? linesValue.filter((line): line is string => typeof line === 'string')
      : typeof latestEvent.data.line === 'string'
        ? [latestEvent.data.line]
        : []

    if (nextLines.length === 0) return

    setAppendedLines(prev => {
      const combined = [...prev, ...nextLines]
      return combined.slice(-limit)
    })
  }, [issueNumber, latestEvent, limit])

  const logTail = useMemo<LogTail | null>(() => {
    const baseLogTail = runLogQuery.data ?? null
    if (!baseLogTail) return null

    const content = appendedLines.length > 0
      ? trimLines([baseLogTail.content, ...appendedLines].filter(Boolean).join('\n'), limit)
      : trimLines(baseLogTail.content, limit)

    const linesReturned = content.length === 0 ? 0 : content.split('\n').length

    return {
      ...baseLogTail,
      content,
      lines_returned: linesReturned,
    }
  }, [appendedLines, limit, runLogQuery.data])

  return {
    ...runLogQuery,
    logTail,
  }
}
