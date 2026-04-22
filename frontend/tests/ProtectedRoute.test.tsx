import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

import { ProtectedRoute } from '@/components/ProtectedRoute'
import { useAuth } from '@/contexts/AuthContext'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)

describe('ProtectedRoute', () => {
  beforeEach(() => {
    mockedUseAuth.mockReset()
  })

  it('renders the session restore state while auth is loading', () => {
    mockedUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      backendState: 'checking',
      backendMessage: null,
      refreshSession: vi.fn(),
      user: null,
      token: null,
      login: vi.fn(),
      register: vi.fn(),
      socialLogin: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <div>Secure area</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Authenticating operator')).toBeInTheDocument()
    expect(screen.queryByText('Secure area')).not.toBeInTheDocument()
  })

  it('renders a deployment-safe unavailable state when the backend is missing', () => {
    mockedUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      backendState: 'unavailable',
      backendMessage: 'https://brav-os-frontend.vercel.app/api/v1/system/health returned 404. This deployment does not have the backend mounted yet.',
      refreshSession: vi.fn(),
      user: null,
      token: null,
      login: vi.fn(),
      register: vi.fn(),
      socialLogin: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <div>Secure area</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Control Plane Unavailable')).toBeInTheDocument()
    expect(screen.getByText('Frontend is live, but the backend is not reachable yet.')).toBeInTheDocument()
    expect(screen.queryByText('Secure area')).not.toBeInTheDocument()
  })

  it('redirects unauthenticated users to login', () => {
    mockedUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      backendState: 'available',
      backendMessage: null,
      refreshSession: vi.fn(),
      user: null,
      token: null,
      login: vi.fn(),
      register: vi.fn(),
      socialLogin: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <div>Secure area</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Secure area')).not.toBeInTheDocument()
  })

  it('renders protected content for authenticated users', () => {
    mockedUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      backendState: 'available',
      backendMessage: null,
      refreshSession: vi.fn(),
      user: {
        id: 'user-1',
        email: 'operator@example.com',
        role: 'admin',
        is_active: true,
        created_at: '2026-04-09T00:00:00Z',
      },
      token: 'access-token',
      login: vi.fn(),
      register: vi.fn(),
      socialLogin: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <div>Secure area</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Secure area')).toBeInTheDocument()
  })
})
