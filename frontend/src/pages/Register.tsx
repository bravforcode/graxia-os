import { useState } from 'react'
import { Link } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { ControlPlaneUnavailable } from '@/components/ControlPlaneUnavailable'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useLang } from '@/i18n/LanguageContext'

export default function Register() {
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { socialLogin, backendState, backendMessage, refreshSession } = useAuth()
  const { t } = useLang()

  const handleGoogleSignup = async () => {
    setError('')
    setIsLoading(true)
    try {
      await socialLogin('google')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('auth.registerFailed'))
      setIsLoading(false)
    }
  }

  if (backendState === 'unavailable') {
    return (
      <AuthShell
        title={t('auth.createAccount')}
        subtitle={t('auth.signInLockedDesc')}
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
      title={t('auth.createAccount')}
      subtitle={t('auth.registerSubtitle')}
    >
      <div className="space-y-5">
        {error ? (
          <div
            role="alert"
            className="rounded-2xl border border-[rgba(239,95,86,0.2)] bg-[rgba(239,95,86,0.08)] px-4 py-3 text-sm text-[var(--color-accent-red)]"
            aria-live="polite"
          >
            {error}
          </div>
        ) : null}

        <Button
          type="button"
          variant="outline"
          className="w-full"
          loading={isLoading}
          onClick={handleGoogleSignup}
        >
          {t('auth.googleSignup')}
        </Button>

        <p className="text-sm text-[var(--color-text-secondary)]">
          {t('auth.passwordRegistrationDisabled')}
        </p>

        <div className="text-sm text-[var(--color-text-secondary)]">
          {t('auth.alreadyHave')}{' '}
          <Link
            className="font-semibold text-[var(--color-accent-cyan)] hover:text-[var(--color-accent-lime)]"
            to="/login"
          >
            {t('auth.signIn')}
          </Link>
        </div>
      </div>
    </AuthShell>
  )
}
