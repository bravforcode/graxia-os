import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { axe } from 'jest-axe'
import { vi } from 'vitest'

import Contacts from '@/pages/Contacts'
import Costs from '@/pages/Costs'
import EmailThreads from '@/pages/EmailThreads'
import EventBus from '@/pages/EventBus'
import Jobs from '@/pages/Jobs'
import Metrics from '@/pages/Metrics'
import Settings from '@/pages/Settings'
import Tasks from '@/pages/Tasks'

const { mockUseOutletContext, mockApi } = vi.hoisted(() => ({
  mockUseOutletContext: vi.fn(),
  mockApi: {
    getContacts: vi.fn(),
    getJobs: vi.fn(),
    getJobStats: vi.fn(),
    getEmailThreads: vi.fn(),
    getEmailStats: vi.fn(),
    markThreadRead: vi.fn(),
    getTasks: vi.fn(),
    getTaskStats: vi.fn(),
    updateTask: vi.fn(),
    completeTask: vi.fn(),
    getCostsSummary: vi.fn(),
    getCostsUsage: vi.fn(),
    getCostsForecast: vi.fn(),
    getMetrics: vi.fn(),
    getScraperHealth: vi.fn(),
    getEventStats: vi.fn(),
    getFailedEvents: vi.fn(),
    getEventHealth: vi.fn(),
    replayFailedEvent: vi.fn(),
    removeFailedEvent: vi.fn(),
    clearFailedEvents: vi.fn(),
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

describe('extended operations page accessibility baseline', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockUseOutletContext.mockReturnValue({
      health: {
        status: 'ok',
        llm_degraded: false,
        llm_cost_paused: false,
        gemini_calls_today: 24,
        scraper_summary: {
          healthy: 3,
          total: 4,
        },
        readiness: {
          is_ready: true,
          mode: 'full',
          issues: ['Google Workspace credentials require rotation.'],
        },
        event_stats: {
          'opportunity.found': 9,
          'draft.generated': 4,
        },
      },
      stats: {
        total_events: 128,
        by_type: {
          'opportunity.found': 9,
          'draft.generated': 4,
        },
      },
      feed: [
        {
          id: 'feed-1',
          title: 'Queue hydrated',
          detail: 'Runtime heartbeat and event snapshots are flowing normally.',
          tone: 'success',
          timestamp: '2026-04-09T10:00:00Z',
          source: 'websocket',
        },
      ],
      refreshRuntime: vi.fn().mockResolvedValue(undefined),
    })

    mockApi.getContacts.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'contact-1',
          name: 'Maya Chen',
          role: 'Founder',
          company: 'Orbit Labs',
          contact_type: 'warm',
          email: 'maya@orbitlabs.dev',
          telegram_handle: '@mayaorbit',
          linkedin_url: 'https://linkedin.com/in/maya-chen',
          relationship_strength: 8,
          notes: 'Warm intro from the accelerator partner network.',
          last_contacted_at: '2026-04-08T14:00:00Z',
        },
      ],
    })

    mockApi.getJobs.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'job-1',
          title: 'Product engineer, AI workflows',
          company: 'Northstar Systems',
          source_platform: 'ashby',
          source_url: 'https://jobs.example.com/ai-workflows',
          location: 'Bangkok / Remote',
          job_type: 'Full-time',
          employment_type: 'Remote-first',
          match_score: 8.6,
          fit_summary: 'Strong overlap with automation systems and applied product work.',
          matched_skills: ['TypeScript', 'Automation'],
          skill_gap_list: ['Rust'],
          status: 'discovered',
          created_at: '2026-04-08T08:00:00Z',
        },
      ],
    })

    mockApi.getJobStats.mockResolvedValue({
      total_jobs: 14,
      by_status: {
        discovered: 8,
        applied: 4,
        rejected: 2,
      },
      average_score: 7.4,
    })

    mockApi.getEmailThreads.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'thread-1',
          thread_id: 'gmail-thread-1',
          subject: 'Follow-up on AI tooling pilot',
          participants: [
            { name: 'Maya Chen', email: 'maya@orbitlabs.dev' },
            { name: 'P', email: 'p@example.com' },
          ],
          category: 'important',
          priority: 8,
          last_message_at: '2026-04-09T11:20:00Z',
          unread_count: 2,
          has_attachments: true,
          action_items: [{ task: 'Send revised pilot scope by Friday.' }],
          status: 'unread',
          created_at: '2026-04-08T07:30:00Z',
          updated_at: '2026-04-09T11:20:00Z',
        },
      ],
    })

    mockApi.getEmailStats.mockResolvedValue({
      total_threads: 18,
      unread_count: 5,
      action_items_count: 7,
      by_category: {
        urgent: 1,
        important: 4,
        normal: 9,
      },
    })

    mockApi.markThreadRead.mockResolvedValue(undefined)

    mockApi.getTasks.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'task-1',
          title: 'Send revised proposal packet',
          description: 'Tighten positioning and include the updated pricing appendix.',
          task_type: 'follow_up',
          priority: 9,
          status: 'pending',
          due_date: '2099-04-10T09:00:00Z',
          related_entity_type: 'draft',
          related_entity_id: 'draft-1',
          assigned_to: 'personal_assistant',
          created_at: '2026-04-09T09:00:00Z',
          updated_at: '2026-04-09T09:30:00Z',
        },
      ],
    })

    mockApi.getTaskStats.mockResolvedValue({
      total_tasks: 12,
      by_status: {
        pending: 5,
        in_progress: 3,
        completed: 4,
      },
      overdue_count: 1,
      due_today_count: 2,
    })

    mockApi.updateTask.mockResolvedValue(undefined)
    mockApi.completeTask.mockResolvedValue(undefined)

    mockApi.getCostsSummary.mockResolvedValue({
      today: { cost_usd: 8.4, budget_usd: 10, percentage: 84 },
      week: { cost_usd: 52, budget_usd: 70, percentage: 74.3 },
      month: { cost_usd: 288, budget_usd: 300, percentage: 96 },
    })

    mockApi.getCostsUsage.mockResolvedValue({
      period_days: 30,
      total_requests: 1860,
      total_cost_usd: 288,
      avg_cost_per_request: 0.15,
      by_platform: {
        ollama: { requests: 980, cost_usd: 0 },
        together: { requests: 620, cost_usd: 188 },
        huggingface: { requests: 260, cost_usd: 100 },
      },
    })

    mockApi.getCostsForecast.mockResolvedValue({
      current_cost: 288,
      forecasted_cost: 342,
      daily_average: 9.6,
      days_elapsed: 30,
      days_remaining: 6,
      budget: 300,
      over_budget: true,
    })

    mockApi.getMetrics.mockResolvedValue([
      {
        id: 'metric-1',
        week_start: '2026-04-06',
        opps_found: 17,
        opps_actioned: 6,
        outreach_sent: 9,
        reply_rate: 44,
        proposals_won: 2,
        revenue_thb: 62000,
        ai_cost_usd: 74,
        avg_energy_this_week: 7.8,
      },
      {
        id: 'metric-2',
        week_start: '2026-03-30',
        opps_found: 13,
        opps_actioned: 4,
        outreach_sent: 7,
        reply_rate: 38,
        proposals_won: 1,
        revenue_thb: 48000,
        ai_cost_usd: 63,
        avg_energy_this_week: 7.1,
      },
    ])

    mockApi.getScraperHealth.mockResolvedValue({
      total_scrapers: 4,
      healthy: 3,
      unhealthy: 1,
      scrapers: [
        {
          name: 'grant-scraper',
          status: 'success',
          last_run_at: '2026-04-09T12:00:00Z',
          time_since_run_seconds: 180,
          results_count: 12,
          error_message: null,
          is_healthy: true,
        },
        {
          name: 'jobs-scraper',
          status: 'error',
          last_run_at: '2026-04-09T11:00:00Z',
          time_since_run_seconds: 3600,
          results_count: 0,
          error_message: 'Quota exceeded for temporary credential.',
          is_healthy: false,
        },
      ],
    })

    mockApi.getEventStats.mockResolvedValue({
      total_events: 128,
      by_type: {
        'opportunity.found': 9,
        'draft.generated': 4,
      },
    })

    mockApi.getFailedEvents.mockResolvedValue({
      total: 1,
      events: [
        {
          index: 7,
          event: 'opportunity.found',
          payload: { opportunity_id: 'opp-1', source: 'grant-scraper' },
          error: 'Downstream scorer unavailable during retry window.',
        },
      ],
    })

    mockApi.getEventHealth.mockResolvedValue({
      status: 'healthy',
      running: true,
      queue_size: 3,
      total_events_processed: 128,
      failed_events: 1,
      event_types: 6,
    })

    mockApi.replayFailedEvent.mockResolvedValue(undefined)
    mockApi.removeFailedEvent.mockResolvedValue(undefined)
    mockApi.clearFailedEvents.mockResolvedValue(undefined)
  })

  it('jobs page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Jobs />)

    await screen.findByText('Product engineer, AI workflows')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('contacts page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Contacts />)

    await screen.findByText('Maya Chen')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('email threads page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<EmailThreads />)

    await screen.findByText('Follow-up on AI tooling pilot')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('tasks page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Tasks />)

    await screen.findByText('Send revised proposal packet')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('metrics page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Metrics />)

    await screen.findAllByText(/Week of/i)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('costs page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Costs />)

    await screen.findByText(/Forecast exceeds budget by/i)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('settings page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<Settings />)

    await screen.findByText('grant-scraper')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('event bus page has no detectable axe violations with loaded data', async () => {
    const { container } = renderWithQueryClient(<EventBus />)

    await screen.findByText('Downstream scorer unavailable during retry window.')

    expect(await axe(container)).toHaveNoViolations()
  })
})
