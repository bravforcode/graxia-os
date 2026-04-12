import type { HTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

type PanelProps = HTMLAttributes<HTMLDivElement> & {
  title?: ReactNode
  eyebrow?: ReactNode
  actions?: ReactNode
}

export function Panel({ title, eyebrow, actions, className, children, ...props }: PanelProps) {
  return (
    <section
      className={cn(
        'rounded-[24px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-5 shadow-[var(--shadow-xl)] backdrop-blur-xl',
        className
      )}
      {...props}
    >
      {(title || eyebrow || actions) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {eyebrow ? (
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                {eyebrow}
              </div>
            ) : null}
            {title ? <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">{title}</h2> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  )
}
