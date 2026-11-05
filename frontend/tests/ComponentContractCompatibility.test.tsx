import { fireEvent, render, screen } from '@testing-library/react'
import { Search } from 'lucide-react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import LeadMagnetPage from '../src/pages/LeadMagnetPage'
import { EmptyState } from '../src/components/ui/empty-state'
import { MetricCard } from '../src/components/ui/metric-card'
import { NoticeBanner } from '../src/components/ui/notice-banner'
import { PageHeader } from '../src/components/ui/page-header'
import { StatusPill } from '../src/components/ui/status-pill'
import { LanguageProvider } from '../src/i18n/LanguageContext'

describe('legacy UI component contracts used by application pages', () => {
  it('renders PageHeader description and actions while retaining children', () => {
    render(
      <PageHeader
        eyebrow="Operations"
        title="Approvals"
        description="Review pending work."
        actions={<button type="button">Refresh</button>}
      >
        <button type="button">Help</button>
      </PageHeader>,
    )

    expect(screen.getByRole('heading', { name: 'Approvals' })).toBeVisible()
    expect(screen.getByText('Review pending work.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Help' })).toBeVisible()
  })

  it('renders MetricCard value, icon, accent, and helper', () => {
    const { container } = render(
      <MetricCard label="Leads" value={42} helper="This week" icon={Search} accent="green" />,
    )

    expect(screen.getByText('42')).toBeVisible()
    expect(screen.getByText('This week')).toBeVisible()
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('accepts the current message prop and the legacy msg prop for EmptyState', () => {
    const { rerender } = render(<EmptyState message="No leads found." />)
    expect(screen.getByText('No leads found.')).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('No leads found.')

    rerender(<EmptyState msg="No jobs found." />)
    expect(screen.getByText('No jobs found.')).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('No jobs found.')
  })

  it('supports neutral status and pulse without dropping the label', () => {
    const { container } = render(<StatusPill label="Queued" tone="neutral" pulse />)

    expect(screen.getByText('Queued')).toBeVisible()
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders NoticeBanner message and invokes its optional dismiss action', () => {
    const onDismiss = vi.fn()
    render(<NoticeBanner tone="danger" message="Delivery failed." onDismiss={onDismiss} />)

    expect(screen.getByText('Delivery failed.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('renders the not-found state and no capture form for an unknown lead magnet', () => {
    render(
      <LanguageProvider>
        <MemoryRouter initialEntries={['/free/not-a-known-magnet']}>
          <Routes>
            <Route path="/free/:slug" element={<LeadMagnetPage />} />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>,
    )

    expect(screen.getByRole('heading', { name: 'Lead magnet not found' })).toBeVisible()
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })
})
