import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, vi } from 'vitest'

import { ErrorBoundary } from '@/components/ErrorBoundary'

function BrokenChild() {
  throw new Error('render failed')
}

describe('ErrorBoundary', () => {
  let consoleError: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    consoleError.mockRestore()
  })

  it('renders a recovery fallback when a child throws', () => {
    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Something broke before the page could recover.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  })
})
