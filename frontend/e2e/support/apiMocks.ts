import type { Page, Route } from '@playwright/test'

type JsonValue = Record<string, unknown> | Array<unknown> | string | number | boolean | null

export type MockSession = {
  accessToken: string
  refreshToken: string
}

export type MockApiState = {
  loginCalls: number
  authMeCalls: number
  checkinCalls: number
  approveDraftCalls: number
  logoutCalls: number
  session: MockSession
  user: {
    id: string
    email: string
    role: string
    is_active: boolean
    created_at: string
  }
  health: {
    status: string
    llm_degraded: boolean
    llm_cost_paused: boolean
    gemini_calls_today: number
    scraper_summary: {
      healthy: number
      total: number
    }
    readiness: {
      is_ready: boolean
      mode: string
      issues: string[]
    }
    event_stats: Record<string, number>
  }
  eventStats: {
    total_events: number
    by_type: Record<string, number>
  }
  opportunities: {
    total: number
    items: Array<Record<string, unknown>>
  }
  drafts: {
    total: number
    items: Array<Record<string, unknown>>
  }
  cognitive: Record<string, unknown>
  metrics: Array<Record<string, unknown>>
  costs: {
    today: {
      cost_usd: number
      budget_usd: number
      percentage: number
    }
    week: {
      cost_usd: number
      budget_usd: number
      percentage: number
    }
    month: {
      cost_usd: number
      budget_usd: number
      percentage: number
    }
  }
}

const jsonHeaders = {
  'access-control-allow-origin': '*',
  'content-type': 'application/json',
}

export function createMockApiState(): MockApiState {
  return {
    loginCalls: 0,
    authMeCalls: 0,
    checkinCalls: 0,
    approveDraftCalls: 0,
    logoutCalls: 0,
    session: {
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    },
    user: {
      id: 'user-1',
      email: 'operator@example.com',
      role: 'admin',
      is_active: true,
      created_at: '2026-04-09T00:00:00Z',
    },
    health: {
      status: 'ok',
      llm_degraded: false,
      llm_cost_paused: false,
      gemini_calls_today: 18,
      scraper_summary: {
        healthy: 3,
        total: 4,
      },
      readiness: {
        is_ready: true,
        mode: 'full',
        issues: [],
      },
      event_stats: {
        'opportunity.found': 12,
        'draft.generated': 4,
      },
    },
    eventStats: {
      total_events: 128,
      by_type: {
        'opportunity.found': 12,
        'draft.generated': 4,
      },
    },
    opportunities: {
      total: 1,
      items: [
        {
          id: 'opp-1',
          type: 'grant',
          title: 'AI Builder Fellowship',
          total_score: 8.7,
          action_priority: 'do_now',
          fit_summary: 'High leverage founder program with strong network upside.',
          found_at: '2026-04-08T08:00:00Z',
          prize_amount: '$25,000',
        },
      ],
    },
    drafts: {
      total: 1,
      items: [
        {
          id: 'draft-1',
          type: 'email',
          title: 'Follow-up to AI Builder Fellowship',
          content: 'Thank you for the opportunity. Here is the sharper version.',
          status: 'pending',
          created_at: '2026-04-08T09:00:00Z',
        },
      ],
    },
    cognitive: {
      id: 'cog-1',
      date: '2026-04-09',
      energy: 7,
      stress: 3,
      available_hours_this_week: 20,
    },
    metrics: [
      {
        id: 'metric-1',
        week_start: '2026-04-07',
        opps_actioned: 4,
        revenue_thb: 48000,
      },
    ],
    costs: {
      today: { cost_usd: 3.42, budget_usd: 10, percentage: 34.2 },
      week: { cost_usd: 19.8, budget_usd: 70, percentage: 28.3 },
      month: { cost_usd: 71.4, budget_usd: 300, percentage: 23.8 },
    },
  }
}

async function fulfillJson(route: Route, payload: JsonValue, status = 200) {
  await route.fulfill({
    status,
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  })
}

export async function installApiMocks(page: Page, state: MockApiState) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    const method = request.method()

    if (method === 'POST' && pathname === '/api/v1/auth/login') {
      state.loginCalls += 1
      await fulfillJson(route, {
        access_token: state.session.accessToken,
        refresh_token: state.session.refreshToken,
        token_type: 'bearer',
        user: state.user,
      })
      return
    }

    if (method === 'POST' && pathname === '/api/v1/auth/logout') {
      state.logoutCalls += 1
      await fulfillJson(route, { message: 'Logged out successfully' })
      return
    }

    if (method === 'GET' && pathname === '/api/v1/auth/me') {
      state.authMeCalls += 1
      await fulfillJson(route, state.user)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/system/health') {
      await fulfillJson(route, state.health)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/events/stats') {
      await fulfillJson(route, state.eventStats)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/opportunities') {
      await fulfillJson(route, state.opportunities)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/drafts') {
      await fulfillJson(route, state.drafts)
      return
    }

    if (method === 'PATCH' && pathname === '/api/v1/drafts/draft-1/approve') {
      state.approveDraftCalls += 1
      state.drafts = {
        total: 0,
        items: [],
      }
      await fulfillJson(route, { ok: true })
      return
    }

    if (method === 'PATCH' && pathname === '/api/v1/drafts/draft-1/reject') {
      state.drafts = {
        total: 0,
        items: [],
      }
      await fulfillJson(route, { ok: true })
      return
    }

    if (method === 'GET' && pathname === '/api/v1/cognitive/today') {
      await fulfillJson(route, state.cognitive)
      return
    }

    if (method === 'POST' && pathname === '/api/v1/cognitive/checkin') {
      state.checkinCalls += 1
      const body = request.postDataJSON() as Record<string, unknown>
      state.cognitive = {
        id: 'cog-1',
        date: '2026-04-09',
        energy: body.energy ?? state.cognitive.energy,
        stress: body.stress ?? state.cognitive.stress,
        available_hours_this_week:
          body.available_hours_this_week ?? state.cognitive.available_hours_this_week,
      }
      await fulfillJson(route, state.cognitive)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/metrics') {
      await fulfillJson(route, state.metrics)
      return
    }

    if (method === 'GET' && pathname === '/api/v1/costs/summary') {
      await fulfillJson(route, state.costs)
      return
    }

    if (method === 'POST' && pathname === '/api/v1/system/scan/now') {
      await fulfillJson(route, { ok: true })
      return
    }

    if (method === 'POST' && pathname === '/api/v1/system/brief/now') {
      await fulfillJson(route, { ok: true })
      return
    }

    await fulfillJson(
      route,
      {
        error: `Unhandled mock route: ${method} ${pathname}`,
      },
      500
    )
  })
}
