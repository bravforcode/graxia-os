import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import ApprovalQueue from '@/pages/ApprovalQueue'

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    getApprovals: vi.fn(),
    approveApproval: vi.fn(),
    rejectApproval: vi.fn(),
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

  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>)
}

describe('ApprovalQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getApprovals.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'approval-1',
          title: 'Send client proposal',
          action_type: 'draft_review',
          status: 'pending',
          policy_class: 'high_impact_external',
          requested_by: 'drafter',
          batch_key: 'draft_review:content_draft:email',
          preview: { content_preview: 'Proposal opening' },
          details: { draft_type: 'email' },
          created_at: '2026-04-20T08:00:00Z',
        },
      ],
    })
    mockApi.approveApproval.mockResolvedValue({
      id: 'approval-1',
      status: 'approved',
      batch_key: 'draft_review:content_draft:email',
    })
    mockApi.rejectApproval.mockResolvedValue({
      id: 'approval-1',
      status: 'rejected',
      batch_key: 'draft_review:content_draft:email',
    })
  })

  it('loads approval requests from the backend API client', async () => {
    renderWithQueryClient(<ApprovalQueue />)

    await screen.findByText('Send client proposal')

    expect(mockApi.getApprovals).toHaveBeenCalledWith({ status: 'pending', limit: 50 })
    expect(screen.getByText('draft_review')).toBeInTheDocument()
    expect(screen.getByText('high_impact_external')).toBeInTheDocument()
  })

  it('approves a pending approval through the backend API client', async () => {
    renderWithQueryClient(<ApprovalQueue />)

    await screen.findByText('Send client proposal')
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => {
      expect(mockApi.approveApproval).toHaveBeenCalledWith('approval-1')
    })
  })

  it('rejects a pending approval with an operator note', async () => {
    renderWithQueryClient(<ApprovalQueue />)

    await screen.findByText('Send client proposal')
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    fireEvent.change(screen.getByPlaceholderText('Why should this action be blocked?'), {
      target: { value: 'Missing client context' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm rejection' }))

    await waitFor(() => {
      expect(mockApi.rejectApproval).toHaveBeenCalledWith('approval-1', 'Missing client context')
    })
  })
})
