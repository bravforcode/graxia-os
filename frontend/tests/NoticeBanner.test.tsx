import { render, screen } from '@testing-library/react'

import { NoticeBanner } from '@/components/ui/notice-banner'

describe('NoticeBanner', () => {
  it('renders non-danger notices as polite status updates', () => {
    render(<NoticeBanner tone="success" message="Saved successfully." />)

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Saved successfully.')).toBeInTheDocument()
  })

  it('renders danger notices as alerts', () => {
    render(<NoticeBanner tone="danger" message="Save failed." />)

    expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive')
    expect(screen.getByText('Save failed.')).toBeInTheDocument()
  })
})
