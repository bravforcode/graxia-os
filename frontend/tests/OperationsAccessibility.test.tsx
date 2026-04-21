import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { vi } from 'vitest'

import Dashboard from '@/pages/Dashboard'
import Drafts from '@/pages/Drafts'
import Opportunities from '@/pages/Opportunities'

const { mockUseOutletContext, mockApi } = vi.hoisted(() => ({
  mockUseOutletContext: vi.fn(),
  mockApi: {
    getOpportunities: vi.fn(),
    approveOpportunity: vi.fn(),
    skipOpportunity: vi.fn(),
    getDrafts: vi.fn(),
    approveDraft: vi.fn(),
    rejectDraft: vi.fn(),
    getCognitiveToday: vi.fn(),
    getMetrics: vi.fn(),
    getCostsSummary: vi.fn(),
    getSystemStats: vi.fn(),
    triggerScan: vi.fn(),
    triggerBrief: vi.fn(),
    checkin: vi.fn(),
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useOutletContext: () => mockUseOutletContext(),
  }
})

vi.mock('@/lib/api', () => ({
  api: mockApi,
}))

function renderWithQueryClient(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>)
}

describe('operations page accessibility baseline', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockUseOutletContext.mockReturnValue({
      health: {
        llm_degraded: false,
        llm_cost_paused: false,
        readiness: {
          mode: 'full',
          issues: [],
        },
      },
      stats: {
        total_events: 128,
        by_type: {
          'opportunity.scored': 4,
        },
      },
      feed: [
        {
          id: 'feed-1',
          title: 'Opportunity scored',
          detail: 'A new opportunity moved into the review queue.',
          tone: 'success',
          timestamp: '2026-04-09T10:00:00Z',
          source: 'polling',
        },
      ],
      refreshRuntime: vi.fn(),
    })

    mockApi.getOpportunities.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'opp-1',
          type: 'grant',
          title: 'AI Builder Fellowship',
          decision: 'do_now',
          action_priority: 'do_now',
          status: 'decided',
          total_score: 8.7,
          fit_summary: 'High leverage founder program with strong network upside.',
          decision_reasoning: 'Best blend of speed, brand, and relationship access.',
          source_platform: 'fellowship-board',
          found_at: '2026-04-08T08:00:00Z',
          tags: ['ai', 'founder'],
        },
      ],
    })

    mockApi.getDrafts.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'draft-1',
          type: 'email',
          title: 'Follow-up to AI Builder Fellowship',
          content: 'Thank you for the opportunity. Here is the sharper version.',
          status: 'pending',
          model_used: 'gemma-4',
          created_at: '2026-04-08T09:00:00Z',
        },
      ],
    })

    mockApi.getCognitiveToday.mockResolvedValue({
      id: 'cog-1',
      date: '2026-04-09',
      energy: 8,
      stress: 3,
      available_hours_this_week: 22,
    })

    mockApi.getMetrics.mockResolvedValue([
      {
        id: 'metric-1',
        week_start: '2026-04-07',
        opps_actioned: 4,
        revenue_thb: 48000,
      },
    ])

    mockApi.getCostsSummary.mockResolvedValue({
      today: { cost_usd: 3.42, budget_usd: 10, percentage: 34.2 },
      week: { cost_usd: 19.8, budget_usd: 70, percentage: 28.3 },
      month: { cost_usd: 71.4, budget_usd: 300, percentage: 23.8 },
    })

    mockApi.getSystemStats.mockResolvedValue({
      leads_scanned: 18,
      active_leads: 7,
      total_contacts: 24,
      opportunities_found: 11,
      ai_actions: 42,
      success_rate: 91.3,
      completed_24h: 5,
      failed_24h: 1,
      outreach_sent_24h: 3,
      active_ai_provider: 'OpenRouter',
      active_ai_model: 'nvidia/nemotron-nano-9b-v2:free',
      environment: 'development',
      history: [
        { name: 'Tue', date: '2026-04-14', leads: 2, outreach: 1, success: 3, failed: 0 },
        { name: 'Wed', date: '2026-04-15', leads: 1, outreach: 2, success: 4, failed: 1 },
        { name: 'Thu', date: '2026-04-16', leads: 3, outreach: 1, success: 5, failed: 0 },
        { name: 'Fri', date: '2026-04-17', leads: 0, outreach: 3, success: 2, failed: 1 },
        { name: 'Sat', date: '2026-04-18', leads: 2, outreach: 0, success: 4, failed: 0 },
        { name: 'Sun', date: '2026-04-19', leads: 1, outreach: 2, success: 3, failed: 0 },
        { name: 'Mon', date: '2026-04-20', leads: 4, outreach: 3, success: 5, failed: 1 },
      ],
    })
  })

  it('dashboard has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Dashboard />)

    await waitFor(() => {
      expect(mockApi.getOpportunities).toHaveBeenCalled()
      expect(mockApi.getDrafts).toHaveBeenCalled()
      expect(screen.getByText('1 open')).toBeInTheDocument()
    })

    expect(await axe(container)).toHaveNoViolations()
  })

  it('drafts page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Drafts />)

    await screen.findByText('Follow-up to AI Builder Fellowship')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('opportunities page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Opportunities />)

    await screen.findByText('AI Builder Fellowship')

    expect(await axe(container)).toHaveNoViolations()
  })
})
