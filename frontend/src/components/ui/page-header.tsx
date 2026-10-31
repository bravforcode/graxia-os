import type { ReactNode } from 'react';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children?: React.ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions, children }: PageHeaderProps) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <div className="text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-cyan)]">
          {eyebrow}
        </div>
      )}
      <div className="mt-2 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            {title}
          </h1>
          {description ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>
        {actions || children ? (
          <div className="flex shrink-0 items-center gap-3">
            {actions}
            {children}
          </div>
        ) : null}
      </div>
    </div>
  );
}
