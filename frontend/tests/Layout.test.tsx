import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

import Layout from '@/components/Layout'

const logout = vi.fn()
const toggleSidebar = vi.fn()
const closeSidebar = vi.fn()

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { email: 'operator@example.com' },
    logout,
  }),
}))

vi.mock('@/hooks/useAgentStream', () => ({
  useAgentStream: () => ({
    connectionState: 'live',
    transport: 'websocket',
    health: {
      llm_degraded: false,
      llm_cost_paused: false,
      readiness: { mode: 'full' },
    },
    stats: { total_events: 128 },
    feed: [],
    refresh: vi.fn(),
  }),
}))

vi.mock('@/store/uiStore', () => ({
  useUIStore: (selector: (state: unknown) => unknown) =>
    selector({
      sidebarOpen: false,
      toggleSidebar,
      closeSidebar,
    }),
}))

describe('Layout', () => {
  it('renders the shell landmarks and skip link', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div>Dashboard body</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main-content')
    expect(screen.getByRole('navigation', { name: 'Sidebar' })).toBeInTheDocument()
    expect(screen.getByText('Dashboard body')).toBeInTheDocument()
    expect(document.getElementById('main-content')).toBeTruthy()

    // Sign out is inside a DropdownMenu — open it first
    await user.click(screen.getByRole('button', { name: /operator/i }))
    expect(await screen.findByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument()
  }, 15000)
})
