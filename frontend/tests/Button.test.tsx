import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Button } from '@/components/ui/button'

describe('Button', () => {
  it('renders children and handles clicks', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Run scan</Button>)

    await userEvent.click(screen.getByRole('button', { name: 'Run scan' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disables the button and shows a spinner when loading', () => {
    render(<Button loading>Saving</Button>)

    const button = screen.getByRole('button', { name: 'Saving' })
    expect(button).toBeDisabled()
    expect(document.querySelector('svg')).toBeTruthy()
  })

  it('defaults to a non-submit button type', () => {
    render(
      <form>
        <Button>Action</Button>
      </form>,
    )

    expect(screen.getByRole('button', { name: 'Action' })).toHaveAttribute('type', 'button')
  })
})
