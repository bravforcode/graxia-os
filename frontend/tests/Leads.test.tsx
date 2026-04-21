import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Leads from '@/pages/Leads'

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    getContacts: vi.fn(),
    getContactStats: vi.fn(),
    createContact: vi.fn(),
    updateContact: vi.fn(),
    deleteContact: vi.fn(),
  },
}))

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

  return render(
    <QueryClientProvider client={queryClient}>
      {node}
    </QueryClientProvider>,
  )
}

describe('Leads page', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockApi.getContacts.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'lead-1',
          name: 'Maya Chen',
          role: 'Founder',
          company: 'Orbit Labs',
          contact_type: 'lead',
          email: 'maya@orbitlabs.dev',
          value_score: 8,
          next_followup_date: '2099-04-24',
          followup_reason: 'Warm intro from partner network',
          notes: 'Strong fit for outreach automation pilot.',
          last_contacted_at: '2099-04-20',
        },
      ],
    })

    mockApi.getContactStats.mockResolvedValue({
      total: 6,
      leads: 4,
      with_email: 3,
      followup_due: 1,
      by_type: {
        lead: 4,
        client: 2,
      },
    })

    mockApi.createContact.mockResolvedValue({
      id: 'lead-2',
      name: 'New Lead',
      contact_type: 'lead',
      value_score: 7,
    })
    mockApi.updateContact.mockResolvedValue({})
    mockApi.deleteContact.mockResolvedValue({})
  })

  it('renders without detectable accessibility violations', async () => {
    const { container } = renderWithQueryClient(<Leads />)

    await screen.findByText('Maya Chen')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('creates a lead from the capture form', async () => {
    const user = userEvent.setup()
    renderWithQueryClient(<Leads />)

    await screen.findByText('Maya Chen')

    await user.type(screen.getByLabelText('Name'), 'Alex Rivera')
    await user.type(screen.getByLabelText('Company'), 'Northstar Systems')
    await user.type(screen.getByLabelText('Email'), 'alex@northstar.dev')
    await user.click(screen.getByRole('button', { name: 'Add lead' }))

    await waitFor(() => {
      expect(mockApi.createContact).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Alex Rivera',
          company: 'Northstar Systems',
          email: 'alex@northstar.dev',
          contact_type: 'lead',
        }),
      )
    })
  })

  it('schedules follow-up directly from the lead card', async () => {
    const user = userEvent.setup()
    renderWithQueryClient(<Leads />)

    await screen.findByText('Maya Chen')
    await user.click(screen.getByRole('button', { name: 'Schedule +3d' }))

    await waitFor(() => {
      expect(mockApi.updateContact).toHaveBeenCalledWith(
        'lead-1',
        expect.objectContaining({
          followup_reason: 'Warm intro from partner network',
        }),
      )
    })
  })
})
