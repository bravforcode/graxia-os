import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    getRuntimeAvailability: vi.fn(),
    getCurrentUser: vi.fn(),
    loginRequest: vi.fn(),
    registerRequest: vi.fn(),
    logoutRequest: vi.fn(),
    socialLogin: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api, { deep: true })

const baseUser = {
  id: 'user-1',
  email: 'operator@example.com',
  role: 'admin',
  is_active: true,
  created_at: '2026-04-09T00:00:00Z',
}

function AuthHarness() {
  const { user, isAuthenticated, isLoading, login, register, logout } = useAuth()

  return (
    <div>
      <div>loading:{String(isLoading)}</div>
      <div>authenticated:{String(isAuthenticated)}</div>
      <div>user:{user?.email ?? 'none'}</div>
      <button onClick={() => void login('operator@example.com', 'secret-password')}>login</button>
      <button onClick={() => void register('new@example.com', 'secret-password', 'New User')}>register</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.getRuntimeAvailability.mockResolvedValue({
      available: true,
      message: 'Backend runtime is reachable.',
      checkedUrl: 'https://example.com/api/v1/system/health',
      status: 200,
    })
    mockedApi.getCurrentUser.mockRejectedValue(new Error('no active session'))
  })

  it('restores the session from the cookie-backed session endpoint', async () => {
    mockedApi.getCurrentUser.mockResolvedValue(baseUser)

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('authenticated:true')).toBeInTheDocument())

    expect(mockedApi.getCurrentUser).toHaveBeenCalledTimes(1)
    expect(screen.getByText(`user:${baseUser.email}`)).toBeInTheDocument()
  })

  it('reports backend unavailability when the runtime probe fails', async () => {
    mockedApi.getRuntimeAvailability.mockResolvedValue({
      available: false,
      message: 'https://example.com/api/v1/system/health returned 404. This deployment does not have the backend mounted yet.',
      checkedUrl: 'https://example.com/api/v1/system/health',
      status: 404,
    })

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('loading:false')).toBeInTheDocument())

    expect(mockedApi.getCurrentUser).not.toHaveBeenCalled()
    expect(screen.getByText('authenticated:false')).toBeInTheDocument()
    expect(screen.getByText('user:none')).toBeInTheDocument()
  })

  it('stores tokens and updates user state on login', async () => {
    mockedApi.loginRequest.mockResolvedValue({
      access_token: 'new-access-token',
      refresh_token: 'new-refresh-token',
      token_type: 'bearer',
      user: baseUser,
    })

    const user = userEvent.setup()

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('loading:false')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByText('authenticated:true')).toBeInTheDocument())

    expect(mockedApi.loginRequest).toHaveBeenCalledWith('operator@example.com', 'secret-password')
    expect(screen.getByText(`user:${baseUser.email}`)).toBeInTheDocument()
  })

  it('clears persisted auth state on logout', async () => {
    mockedApi.loginRequest.mockResolvedValue({
      access_token: 'new-access-token',
      refresh_token: 'new-refresh-token',
      token_type: 'bearer',
      user: baseUser,
    })

    const user = userEvent.setup()

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByText('loading:false')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'login' }))
    await waitFor(() => expect(screen.getByText('authenticated:true')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'logout' }))

    expect(mockedApi.logoutRequest).toHaveBeenCalledTimes(1)
    expect(screen.getByText('authenticated:false')).toBeInTheDocument()
    expect(screen.getByText('user:none')).toBeInTheDocument()
  })
})
