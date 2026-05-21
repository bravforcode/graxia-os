import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Dialog } from '@/components/ui/dialog'

describe('Dialog', () => {
  it('renders dialog content when open', () => {
    render(
      <Dialog open title="Confirm" onClose={() => {}}>
        <div>Body copy</div>
      </Dialog>
    )

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Confirm')).toBeInTheDocument()
    expect(screen.getByText('Body copy')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    render(
      <Dialog open title="Confirm" onClose={onClose}>
        <div>Body copy</div>
      </Dialog>
    )

    await userEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes when escape is pressed', async () => {
    const onClose = vi.fn()
    render(
      <Dialog open title="Confirm" onClose={onClose}>
        <input aria-label="Reason" />
      </Dialog>
    )

    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('traps focus inside the dialog', async () => {
    render(
      <Dialog
        open
        title="Confirm"
        onClose={() => {}}
        footer={<button type="button">Confirm action</button>}
      >
        <input aria-label="Reason" />
      </Dialog>
    )

    const closeButton = screen.getByRole('button', { name: 'Close dialog' })
    const reasonInput = screen.getByRole('textbox', { name: 'Reason' })
    const confirmButton = screen.getByRole('button', { name: 'Confirm action' })

    expect(closeButton).toHaveFocus()

    await userEvent.tab()
    expect(reasonInput).toHaveFocus()

    await userEvent.tab()
    expect(confirmButton).toHaveFocus()

    await userEvent.tab()
    expect(closeButton).toHaveFocus()
  })
})
