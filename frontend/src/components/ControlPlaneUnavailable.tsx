import { RefreshCw, ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/Button'

type ControlPlaneUnavailableProps = {
  message: string
  onRetry?: () => Promise<void> | void
}

export function ControlPlaneUnavailable({ message, onRetry }: ControlPlaneUnavailableProps) {
  return (
    <section
      role="status"
      aria-live="polite"
      className="rounded-[28px] border border-[rgba(239,95,86,0.22)] bg-[rgba(239,95,86,0.08)] p-6 shadow-[var(--shadow-lg)]"
    >
      <div className="flex items-start gap-4">
        <div className="rounded-2xl border border-[rgba(239,95,86,0.24)] bg-[rgba(239,95,86,0.12)] p-3 text-[var(--color-accent-red)]">
          <ShieldAlert size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-red)]">
            Control Plane Unavailable
          </p>
          <h2 className="mt-3 text-2xl font-semibold text-[var(--color-text-primary)]">
            Frontend is live, but the backend is not reachable yet.
          </h2>
          <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
            Sign-in, registration, and operator actions stay locked until the API health surface responds.
          </p>
          <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{message}</p>
          {onRetry ? (
            <div className="mt-5">
              <Button variant="outline" onClick={() => void onRetry()} icon={<RefreshCw size={16} />}>
                Retry connection
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}
