import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

import { Dialog } from '@/components/ui/Dialog'
import Layout from '@/components/Layout'
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import { ProtectedRoute } from '@/components/ProtectedRoute'

const logout = vi.fn()
const login = vi.fn()
const register = vi.fn()
const refresh = vi.fn()
const toggleSidebar = vi.fn()
const closeSidebar = vi.fn()

type MockAuthState = {
  user: { email: string } | null
  token: string | null
  login: typeof login
  register: typeof register
  socialLogin: typeof login
  logout: typeof logout
  isAuthenticated: boolean
  isLoading: boolean
  backendState: 'checking' | 'available' | 'unavailable'
  backendMessage: string | null
  refreshSession: typeof refresh
}

let authState: MockAuthState = {
  user: { email: 'operator@example.com' },
  token: 'token',
  login,
  register,
  socialLogin: login,
  logout,
  isAuthenticated: true,
  isLoading: false,
  backendState: 'available',
  backendMessage: null,
  refreshSession: refresh,
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

vi.mock('@/hooks/useAgentStream', () => ({
  useAgentStream: () => ({
    connectionState: 'live',
    transport: 'websocket',
    health: {
      llm_degraded: false,
      llm_cost_paused: false,
      readiness: {
        is_ready: true,
        mode: 'full',
        issues: [],
      },
      scraper_summary: {
        healthy: 3,
        total: 3,
      },
      gemini_calls_today: 0,
      event_stats: {},
      status: 'healthy',
    },
    stats: {
      total_events: 128,
      by_type: {},
    },
    feed: [],
    refresh,
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

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>)
}

describe('frontend accessibility baseline', () => {
  beforeEach(() => {
    authState = {
      user: { email: 'operator@example.com' },
      token: 'token',
      login,
      register,
      socialLogin: login,
      logout,
      isAuthenticated: true,
      isLoading: false,
      backendState: 'available',
      backendMessage: null,
      refreshSession: refresh,
    }
  })

  it('login page has no detectable axe violations', async () => {
    const { container } = renderWithProviders(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Login />
      </MemoryRouter>,
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('register page has no detectable axe violations', async () => {
    const { container } = renderWithProviders(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Register />
      </MemoryRouter>,
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('protected-route loading state has no detectable axe violations', async () => {
    authState = {
      user: null,
      token: null,
      login,
      register,
      socialLogin: login,
      logout,
      isAuthenticated: false,
      isLoading: true,
      backendState: 'checking',
      backendMessage: null,
      refreshSession: refresh,
    }

    const { container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProtectedRoute>
          <div>Secure area</div>
        </ProtectedRoute>
      </MemoryRouter>,
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('dialog primitive has no detectable axe violations', async () => {
    const { container } = render(
      <Dialog
        open
        title="Confirm action"
        description="Review the consequences before continuing."
        onClose={() => {}}
        footer={<button type="button">Confirm</button>}
      >
        <label>
          Reason
          <textarea />
        </label>
      </Dialog>,
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('application shell baseline has no detectable axe violations', async () => {
    const { container } = renderWithProviders(
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

    expect(await axe(container)).toHaveNoViolations()
  })
})
