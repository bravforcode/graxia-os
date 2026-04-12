import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

type MetricCardProps = {
  label: string
  value: string
  helper?: string
  accent?: 'cyan' | 'green' | 'orange' | 'blue'
  icon: LucideIcon
  className?: string
}

const accentClasses = {
  cyan: 'text-[var(--color-accent-cyan)]',
  green: 'text-[var(--color-accent-green)]',
  orange: 'text-[var(--color-accent-orange)]',
  blue: 'text-[var(--color-accent-blue)]',
}

export function MetricCard({
  label,
  value,
  helper,
  accent = 'cyan',
  icon: Icon,
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        'rounded-[22px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-5 shadow-[var(--shadow-lg)]',
        className
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-[var(--color-text-secondary)]">{label}</span>
        <Icon size={18} className={accentClasses[accent]} />
      </div>
      <div className="text-3xl font-semibold tracking-tight text-[var(--color-text-primary)]">{value}</div>
      {helper ? <div className="mt-2 text-sm text-[var(--color-text-tertiary)]">{helper}</div> : null}
    </div>
  )
}
