import { useEffect, useRef, useState } from 'react'

import { api, type EventStats, type SystemHealth } from '@/lib/api'

function getStoredAccessToken(): string | null {
  try {
    // Read access token from httpOnly cookie is not possible in JS;
    // try Authorization header cache stored by the API layer if available.
    // Fallback: nothing — WS will degrade to polling if no token.
    const raw = document.cookie
      .split('; ')
      .find((row) => row.startsWith('access_token='))
    return raw ? raw.split('=').slice(1).join('=') : null
  } catch {
    return null
  }
}

export type AgentFeedTone = 'neutral' | 'success' | 'warning' | 'danger'
export type AgentConnectionState = 'connecting' | 'live' | 'fallback' | 'offline'
export type AgentTransport = 'websocket' | 'polling'

export type AgentFeedItem = {
  id: string
  title: string
  detail: string
  tone: AgentFeedTone
  timestamp: string
  source: string
}

type AgentStreamSnapshot = {
  health: SystemHealth | null
  stats: EventStats | null
}

const POLL_INTERVAL_MS = 10_000
const MAX_FEED_ITEMS = 24

function makeFeedItem(
  title: string,
  detail: string,
  tone: AgentFeedTone,
  source: string,
  timestamp = new Date().toISOString()
): AgentFeedItem {
  return {
    id: `${source}-${title}-${timestamp}-${Math.random().toString(36).slice(2, 8)}`,
    title,
    detail,
    tone,
    source,
    timestamp,
  }
}

function summarizeDelta(previous: EventStats | null, next: EventStats): AgentFeedItem[] {
  if (!previous) {
    return [
      makeFeedItem(
        'Stream primed',
        `${next.total_events} events observed across ${Object.keys(next.by_type).length} event types.`,
        'neutral',
        'polling'
      ),
    ]
  }

  const entries = Object.entries(next.by_type)
    .map(([eventType, count]) => [eventType, count - (previous.by_type[eventType] ?? 0)] as const)
    .filter(([, delta]) => delta > 0)
    .sort((left, right) => right[1] - left[1])

  return entries.map(([eventType, delta]) =>
    makeFeedItem(
      `${eventType} advanced`,
      `${delta} new event${delta > 1 ? 's' : ''} processed since the last snapshot.`,
      eventType.includes('failed') || eventType.includes('error') ? 'warning' : 'success',
      'polling'
    )
  )
}

function summarizeHealth(previous: SystemHealth | null, next: SystemHealth): AgentFeedItem[] {
  if (!previous) {
    return [
      makeFeedItem(
        'Runtime snapshot loaded',
        `Mode ${next.readiness.mode}. LLM ${next.llm_degraded ? 'degraded' : 'healthy'}.`,
        next.status === 'ok' ? 'success' : 'warning',
        'polling'
      ),
    ]
  }

  const feed: AgentFeedItem[] = []

  if (previous.readiness.mode !== next.readiness.mode) {
    feed.push(
      makeFeedItem(
        'Readiness mode changed',
        `Runtime moved from ${previous.readiness.mode} to ${next.readiness.mode}.`,
        next.readiness.mode === 'full' ? 'success' : 'warning',
        'polling'
      )
    )
  }

  if (previous.llm_degraded !== next.llm_degraded) {
    feed.push(
      makeFeedItem(
        next.llm_degraded ? 'LLM degraded' : 'LLM recovered',
        next.llm_degraded
          ? 'The runtime is using degraded AI behavior.'
          : 'Primary AI behavior is available again.',
        next.llm_degraded ? 'warning' : 'success',
        'polling'
      )
    )
  }

  if (previous.llm_cost_paused !== next.llm_cost_paused) {
    feed.push(
      makeFeedItem(
        next.llm_cost_paused ? 'AI budget pause active' : 'AI budget pause cleared',
        next.llm_cost_paused
          ? 'Cost controls paused AI-heavy work.'
          : 'AI-heavy work is available again.',
        next.llm_cost_paused ? 'danger' : 'success',
        'polling'
      )
    )
  }

  return feed
}

function normalizeWebSocketUrl(value: string) {
  if (value.startsWith('ws://') || value.startsWith('wss://')) {
    return value
  }
  if (value.startsWith('http://')) {
    return `ws://${value.slice('http://'.length)}`
  }
  if (value.startsWith('https://')) {
    return `wss://${value.slice('https://'.length)}`
  }
  return value
}

export function useAgentStream() {
  const [connectionState, setConnectionState] = useState<AgentConnectionState>('connecting')
  const [transport, setTransport] = useState<AgentTransport>('polling')
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [stats, setStats] = useState<EventStats | null>(null)
  const [feed, setFeed] = useState<AgentFeedItem[]>([])
  const previousRef = useRef<AgentStreamSnapshot>({ health: null, stats: null })
  const stopPollingRef = useRef<(() => void) | null>(null)

  async function pollOnce() {
    try {
      const [nextHealth, nextStats] = await Promise.all([api.getHealth(), api.getEventStats()])
      const nextFeed = [
        ...summarizeHealth(previousRef.current.health, nextHealth),
        ...summarizeDelta(previousRef.current.stats, nextStats),
      ]

      previousRef.current = { health: nextHealth, stats: nextStats }
      setHealth(nextHealth)
      setStats(nextStats)
      setFeed((current) => [...nextFeed, ...current].slice(0, MAX_FEED_ITEMS))
      setConnectionState((current) => (current === 'live' ? current : 'fallback'))
      setTransport('polling')
    } catch {
      setConnectionState('offline')
    }
  }

  useEffect(() => {
    let intervalId: number | undefined
    let socket: WebSocket | null = null
    let disposed = false

    const startPolling = () => {
      stopPollingRef.current?.()
      void pollOnce()
      intervalId = window.setInterval(() => {
        void pollOnce()
      }, POLL_INTERVAL_MS)
      stopPollingRef.current = () => {
        if (intervalId !== undefined) {
          window.clearInterval(intervalId)
        }
      }
    }

    const wsUrl = normalizeWebSocketUrl(import.meta.env.VITE_AGENT_STREAM_URL?.trim?.() ?? '')
    if (!wsUrl) {
      startPolling()
      return () => {
        disposed = true
        stopPollingRef.current?.()
      }
    }

    try {
      const url = new URL(wsUrl)
      const token = getStoredAccessToken()
      if (token) {
        url.searchParams.set('token', token)
      }
      socket = new WebSocket(url.toString())
      setTransport('websocket')
      setConnectionState('connecting')

      socket.onopen = () => {
        setConnectionState('live')
        setFeed((current) =>
          [
            makeFeedItem(
              'Live stream connected',
              'WebSocket transport is active for agent activity.',
              'success',
              'websocket'
            ),
            ...current,
          ].slice(0, MAX_FEED_ITEMS)
        )
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            title?: string
            detail?: string
            tone?: AgentFeedTone
            source?: string
            timestamp?: string
            health?: SystemHealth
            stats?: EventStats
          }

          if (payload.health) {
            setHealth(payload.health)
          }
          if (payload.stats) {
            setStats(payload.stats)
          }

          setFeed((current) =>
            [
              makeFeedItem(
                payload.title ?? 'Agent activity',
                payload.detail ?? 'A realtime agent event was received.',
                payload.tone ?? 'neutral',
                payload.source ?? 'websocket',
                payload.timestamp
              ),
              ...current,
            ].slice(0, MAX_FEED_ITEMS)
          )
        } catch {
          setFeed((current) =>
            [
              makeFeedItem(
                'Unparsed stream event',
                'Received a websocket message that did not match the expected shape.',
                'warning',
                'websocket'
              ),
              ...current,
            ].slice(0, MAX_FEED_ITEMS)
          )
        }
      }

      socket.onerror = () => {
        if (!disposed) {
          startPolling()
        }
      }

      socket.onclose = () => {
        if (!disposed) {
          startPolling()
        }
      }
    } catch {
      startPolling()
    }

    return () => {
      disposed = true
      socket?.close()
      stopPollingRef.current?.()
    }
  }, [])

  return {
    connectionState,
    transport,
    health,
    stats,
    feed,
    refresh: pollOnce,
  }
}
