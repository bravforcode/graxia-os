import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import Login from '@/pages/Login'
import Register from '@/pages/Register'

const login = vi.fn()
const register = vi.fn()
const socialLogin = vi.fn()
const logout = vi.fn()
const refreshSession = vi.fn()

type MockAuthState = {
  user: null
  token: null
  login: typeof login
  register: typeof register
  socialLogin: typeof socialLogin
  logout: typeof logout
  isAuthenticated: boolean
  isLoading: boolean
  backendState: 'checking' | 'available' | 'unavailable'
  backendMessage: string | null
  refreshSession: typeof refreshSession
}

let authState: MockAuthState = {
  user: null,
  token: null,
  login,
  register,
  socialLogin,
  logout,
  isAuthenticated: false,
  isLoading: false,
  backendState: 'unavailable',
  backendMessage: 'https://brav-os-frontend.vercel.app/api/v1/system/health returned 404. This deployment does not have the backend mounted yet.',
  refreshSession,
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

describe('auth pages when the backend is unavailable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState = {
      user: null,
      token: null,
      login,
      register,
      socialLogin,
      logout,
      isAuthenticated: false,
      isLoading: false,
      backendState: 'unavailable',
      backendMessage: 'https://brav-os-frontend.vercel.app/api/v1/system/health returned 404. This deployment does not have the backend mounted yet.',
      refreshSession,
    }
  })

  it('shows the deployment-safe unavailable state on login and retries on demand', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Login />
      </MemoryRouter>,
    )

    expect(screen.getByText('Control Plane Unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry connection' }))

    expect(refreshSession).toHaveBeenCalledTimes(1)
  })

  it('shows the deployment-safe unavailable state on register', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Register />
      </MemoryRouter>,
    )

    expect(screen.getByText('Control Plane Unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create account' })).not.toBeInTheDocument()
  })
})
