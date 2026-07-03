import { StatusPill } from '@/components/ui/status-pill'

export type NoticeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

type NoticeBannerProps = {
  tone: NoticeTone
  message: string
  onDismiss?: () => void
}

export function NoticeBanner({ tone, message, onDismiss }: NoticeBannerProps) {
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      aria-live={tone === 'danger' ? 'assertive' : 'polite'}
      className="rounded-[24px] border border-[var(--color-border)] bg-[var(--panel-bg)] px-4 py-4 shadow-[var(--shadow-lg)]"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <StatusPill label={tone} tone={tone} />
          <div className="text-sm text-[var(--color-text-secondary)]">{message}</div>
        </div>
        {onDismiss ? (
          <button
            type="button"
            className="text-sm text-[var(--color-text-tertiary)] transition hover:text-[var(--color-text-primary)]"
            onClick={onDismiss}
          >
            Dismiss
          </button>
        ) : null}
      </div>
    </div>
  )
}
