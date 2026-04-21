import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentStream } from '@/hooks/useAgentStream'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getAccessToken: vi.fn(() => null),
  api: {
    getHealth: vi.fn(),
    getEventStats: vi.fn(),
  },
}))

describe('useAgentStream', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('VITE_AGENT_STREAM_URL', '')
    vi.mocked(api.getHealth).mockResolvedValue({
      status: 'ok',
      llm_degraded: false,
      llm_cost_paused: false,
      gemini_calls_today: 4,
      scraper_summary: { healthy: 2, total: 2 },
      readiness: {
        is_ready: true,
        mode: 'full',
        issues: [],
        updated_at: '2026-04-09T00:00:00Z',
      },
      event_stats: {
        opportunity_found: 2,
      },
    })
    vi.mocked(api.getEventStats).mockResolvedValue({
      total_events: 2,
      by_type: {
        opportunity_found: 2,
      },
    })
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('falls back to polling when no websocket url is configured', async () => {
    const { result } = renderHook(() => useAgentStream())

    await waitFor(() => {
      expect(result.current.transport).toBe('polling')
      expect(result.current.connectionState).toBe('fallback')
    })

    expect(result.current.health?.readiness.mode).toBe('full')
    expect(result.current.stats?.total_events).toBe(2)
    expect(result.current.feed.length).toBeGreaterThan(0)
  })
})
