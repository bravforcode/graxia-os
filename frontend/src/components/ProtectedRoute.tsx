import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { useAuth } from '@/contexts/AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { isAuthenticated, isLoading, backendState, backendMessage, refreshSession } = useAuth()

  if (isLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-6 text-center"
        role="status"
        aria-live="polite"
      >
        <div className="panel max-w-md space-y-3 p-8">
          <p className="eyebrow">Session Restore</p>
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Authenticating operator
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Rehydrating your control plane access and reconnecting agent telemetry.
          </p>
        </div>
      </div>
    )
  }

  if (backendState === 'unavailable') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-6 py-10">
        <div className="w-full max-w-3xl">
          <ControlPlaneUnavailable
            message={
              backendMessage ??
              'The backend control plane is not reachable from this deployment yet.'
            }
            onRetry={refreshSession}
          />
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <>{children}</>
}
