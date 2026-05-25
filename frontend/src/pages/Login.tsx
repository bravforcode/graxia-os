import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { login, socialLogin, backendState, backendMessage, refreshSession } = useAuth()
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

  if (backendState === 'unavailable') {
    return (
      <AuthShell
        title="Sign-in locked"
        subtitle="The operator API is not reachable from this deployment yet."
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
      title="Log in to Graxia OS"
      subtitle="Enter your details to access your workspace."
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        {error ? (
          <div
            role="alert"
            className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-500"
            aria-live="polite"
          >
            {error}
          </div>
        ) : null}

        <div className="space-y-1.5">
          <label htmlFor="email" className="block text-sm font-medium text-zinc-300">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="w-full rounded-md border border-zinc-800 bg-black px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            placeholder="user@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="password" className="block text-sm font-medium text-zinc-300">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="w-full rounded-md border border-zinc-800 bg-black px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        <Button type="submit" className="w-full bg-white text-black hover:bg-zinc-200" loading={isLoading}>
          Continue with Email
        </Button>

        <div className="relative py-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-zinc-800"></div>
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-black px-2 text-zinc-500">Or continue with</span>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full border-zinc-800 bg-black text-white hover:bg-zinc-900 hover:text-white"
          onClick={() => socialLogin('google')}
        >
          Google
        </Button>

        <p className="text-center text-sm text-zinc-500 pt-2">
          Don't have an account?{' '}
          <Link className="font-medium text-white hover:underline" to="/register">
            Sign up
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
