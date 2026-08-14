import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useLang } from '@/i18n/LanguageContext'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { register, backendState, backendMessage, refreshSession } = useAuth()
  const navigate = useNavigate()
  const { t } = useLang()

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError(t('auth.passwordsMismatch'))
      return
    }

    if (password.length < 8) {
      setError(t('auth.passwordTooShort'))
      return
    }

    setIsLoading(true)

    try {
      await register(email, password, fullName)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('auth.registerFailed'))
    } finally {
      setIsLoading(false)
    }
  }

  if (backendState === 'unavailable') {
    return (
      <AuthShell
        title={t("auth.createAccount")}
        subtitle={t("auth.signInLockedDesc")}
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
      title={t("auth.createAccount")}
      subtitle={t("auth.registerSubtitle")}
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
          <span>{t("auth.fullName")}</span>
          <input
            id="fullName"
            name="fullName"
            type="text"
            className="input-field"
            placeholder={t("auth.optionalDisplayName")}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>{t("auth.email")}</span>
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
            <span>{t("auth.password")}</span>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              className="input-field"
              placeholder={t("auth.min8")}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>{t("auth.confirmPassword")}</span>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              className="input-field"
              placeholder={t("auth.repeatPassword")}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </label>
        </div>

        <Button type="submit" className="w-full" loading={isLoading}>
          {t("auth.createAccount")}
        </Button>

        <div className="text-sm text-[var(--color-text-secondary)]">
          {t("auth.alreadyHave")}{' '}
          <Link className="font-semibold text-[var(--color-accent-cyan)] hover:text-[var(--color-accent-lime)]" to="/login">
            {t("auth.signIn")}
          </Link>
        </div>
      </form>
    </AuthShell>
  )
}
