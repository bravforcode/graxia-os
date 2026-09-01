import { cn } from '@/lib/utils'

type StatusTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

const toneClasses: Record<StatusTone, string> = {
  neutral: 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]',
  success: 'bg-[rgba(63,185,80,0.16)] text-[var(--color-accent-green)]',
  warning: 'bg-[rgba(240,136,62,0.16)] text-[var(--color-accent-orange)]',
  danger: 'bg-[rgba(218,54,51,0.16)] text-[var(--color-accent-red)]',
  info: 'bg-[rgba(0,212,255,0.16)] text-[var(--color-accent-cyan)]',
}

type StatusPillProps = {
  label: string
  tone?: StatusTone
  pulse?: boolean
}

export function StatusPill({ label, tone = 'neutral', pulse = false }: StatusPillProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]',
        toneClasses[tone]
      )}
    >
      <span className={cn('h-2 w-2 rounded-full bg-current', pulse ? 'animate-pulse' : '')} />
      {label}
    </span>
  )
}
