/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import axios from 'axios'
import { api, type User } from '@/lib/api'

interface AuthContextType {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void
  isAuthenticated: boolean
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function isExpectedUnauthenticatedError(error: unknown) {
  if (axios.isAxiosError(error)) {
    return error.response?.status === 401
  }
  return error instanceof Error && error.message === 'no active session'
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    void fetchUser()

    const handleSessionExpired = () => {
      setUser(null)
      setToken(null)
      setIsLoading(false)
    }

    window.addEventListener('auth:session-expired', handleSessionExpired)
    return () => window.removeEventListener('auth:session-expired', handleSessionExpired)
  }, [])

  const fetchUser = async () => {
    try {
      const currentUser = await api.getCurrentUser()
      setUser(currentUser)
      setToken('session')
    } catch (error) {
      if (!isExpectedUnauthenticatedError(error)) {
        console.error('Failed to fetch user:', error)
      }
      setUser(null)
      setToken(null)
    } finally {
      setIsLoading(false)
    }
  }

  // Login
  const login = async (email: string, password: string) => {
    try {
      const response = await api.loginRequest(email, password)
      setUser(response.user)
      setToken('session')
    } catch (error: unknown) {
      throw new Error(error instanceof Error ? error.message : 'Login failed')
    }
  }

  // Register
  const register = async (email: string, password: string, fullName?: string) => {
    try {
      const response = await api.registerRequest(email, password, fullName)
      setUser(response.user)
      setToken('session')
    } catch (error: unknown) {
      throw new Error(error instanceof Error ? error.message : 'Registration failed')
    }
  }

  // Logout
  const logout = () => {
    void api.logoutRequest()
    setUser(null)
    setToken(null)
  }

  const value: AuthContextType = {
    user,
    token,
    login,
    register,
    logout,
    isAuthenticated: !!user,
    isLoading
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
