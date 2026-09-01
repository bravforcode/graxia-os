import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

type MetricCardProps = {
  /** UI-style header text (used by most pages). */
  label?: string
  /** Admin-style header text (alias of label). */
  title?: string
  value: string | number
  /** UI-style sub text. */
  helper?: string
  /** Admin-style sub text (alias of helper). */
  subtitle?: string
  accent?: 'cyan' | 'green' | 'orange' | 'blue'
  icon?: LucideIcon
  status?: 'up' | 'down' | 'neutral' | 'warning' | 'critical'
  className?: string
}

const accentClasses = {
  cyan: 'text-[var(--color-accent-cyan)]',
  green: 'text-[var(--color-accent-green)]',
  orange: 'text-[var(--color-accent-orange)]',
  blue: 'text-[var(--color-accent-blue)]',
}

const statusColors: Record<string, { border: string; dot: string }> = {
  up: { border: 'border-emerald-500/30', dot: 'bg-emerald-400' },
  down: { border: 'border-red-500/30', dot: 'bg-red-400' },
  neutral: { border: 'border-zinc-700', dot: 'bg-zinc-400' },
  warning: { border: 'border-amber-500/30', dot: 'bg-amber-400' },
  critical: { border: 'border-red-500/50', dot: 'bg-red-400' },
}

export function MetricCard({
  label,
  title,
  value,
  helper,
  subtitle,
  accent = 'cyan',
  icon: Icon,
  status,
  className,
}: MetricCardProps) {
  const headerText = label ?? title ?? ''
  const subText = helper ?? subtitle

  // Admin-style: status-driven border + status dot (dark zinc theme).
  if (status !== undefined || title !== undefined) {
    const colors = statusColors[status ?? 'neutral']
    return (
      <div
        className={cn(
          'rounded-xl border bg-zinc-900/60 p-4 backdrop-blur-sm transition-colors hover:bg-zinc-900/80',
          colors.border,
          className
        )}
      >
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">{headerText}</span>
          {status ? <span className={cn('h-2 w-2 rounded-full', colors.dot)} /> : null}
        </div>
        <div className="text-2xl font-semibold tracking-tight text-white">{value}</div>
        {subText ? <div className="mt-1 text-xs text-zinc-500">{subText}</div> : null}
      </div>
    )
  }

  // UI-style: icon + accent (light theme).
  return (
    <div
      className={cn(
        'rounded-[22px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-5 shadow-[var(--shadow-lg)]',
        className
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-[var(--color-text-secondary)]">{headerText}</span>
        {Icon ? <Icon size={18} className={accentClasses[accent]} /> : null}
      </div>
      <div className="text-3xl font-semibold tracking-tight text-[var(--color-text-primary)]">{value}</div>
      {subText ? <div className="mt-2 text-sm text-[var(--color-text-tertiary)]">{subText}</div> : null}
    </div>
  )
}
