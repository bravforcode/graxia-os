import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useLang } from '@/i18n/LanguageContext'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { login, socialLogin, backendState, backendMessage, refreshSession } = useAuth()
  const { t } = useLang()
  const navigate = useNavigate()

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      await login(email, password)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('auth.loginFailed'))
    } finally {
      setIsLoading(false)
    }
  }

  if (backendState === 'unavailable') {
    return (
      <AuthShell
        title={t("auth.signInLocked")}
        subtitle={t("auth.signInLockedDesc")}
      >
        <ControlPlaneUnavailable
          message={backendMessage ?? t('auth.signInLockedDesc')}
          onRetry={refreshSession}
        />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={t("auth.title")}
      subtitle={t("auth.subtitle")}
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
            {t("auth.email")}
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
            {t("auth.password")}
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
          {t("auth.continue")}
        </Button>

        <div className="relative py-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-zinc-800"></div>
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-black px-2 text-zinc-500">{t("auth.orContinue")}</span>
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
          {t("auth.noAccount")}{' '}
          <Link className="font-medium text-white hover:underline" to="/register">
            {t("auth.signUp")}
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
