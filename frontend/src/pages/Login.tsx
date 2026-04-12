import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/contexts/AuthContext'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      await login(email, password)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Authenticate into the operator console to review drafts, monitor agent health, and control automation."
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

        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>Password</span>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="input-field"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <Button type="submit" className="w-full" loading={isLoading}>
          Sign in
        </Button>

        <div className="text-sm text-[var(--color-text-secondary)]">
          New operator?{' '}
          <Link className="font-semibold text-[var(--color-accent-cyan)] hover:text-[var(--color-accent-lime)]" to="/register">
            Create an account
          </Link>
        </div>
      </form>
    </AuthShell>
  )
}
