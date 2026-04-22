import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/contexts/AuthContext'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { register, backendState, backendMessage, refreshSession } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setIsLoading(true)

    try {
      await register(email, password, fullName)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }

  if (backendState === 'unavailable') {
    return (
      <AuthShell
        title="Create account"
        subtitle="Provision operator access after the backend control plane is reachable."
      >
        <ControlPlaneUnavailable
          message={backendMessage ?? 'The operator API is not reachable from this deployment yet.'}
          onRetry={refreshSession}
        />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Create account"
      subtitle="Provision a new operator identity for the Personal OS control plane with a clean, role-ready login."
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        {error ? (
          <div
            role="alert"
            className="rounded-2xl border border-[rgba(239,95,86,0.2)] bg-[rgba(239,95,86,0.08)] px-4 py-3 text-sm text-[var(--color-accent-red)]"
            aria-live="polite"
          >
            {error}
          </div>
        ) : null}

        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>Full name</span>
          <input
            id="fullName"
            name="fullName"
            type="text"
            className="input-field"
            placeholder="Optional display name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>Email</span>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="input-field"
            placeholder="you@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <div className="grid gap-5 sm:grid-cols-2">
          <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Password</span>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              className="input-field"
              placeholder="Minimum 8 characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Confirm password</span>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              className="input-field"
              placeholder="Repeat password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </label>
        </div>

        <Button type="submit" className="w-full" loading={isLoading}>
          Create account
        </Button>

        <div className="text-sm text-[var(--color-text-secondary)]">
          Already have access?{' '}
          <Link className="font-semibold text-[var(--color-accent-cyan)] hover:text-[var(--color-accent-lime)]" to="/login">
            Sign in
          </Link>
        </div>
      </form>
    </AuthShell>
  )
}
