import type { LucideIcon } from 'lucide-react';

type Accent = 'cyan' | 'green' | 'orange' | 'blue';

interface MetricCardBaseProps {
  label: string;
  helper?: string;
  icon?: LucideIcon;
  accent?: Accent;
}

type MetricCardProps = MetricCardBaseProps & (
  | { value: string | number; val?: string | number }
  | { val: string | number; value?: string | number }
);

const accentClasses: Record<Accent, string> = {
  cyan: 'text-[var(--color-accent-cyan)]',
  green: 'text-[var(--color-accent-green)]',
  orange: 'text-[var(--color-accent-orange)]',
  blue: 'text-[var(--color-accent-blue)]',
};

export function MetricCard({ label, value, val, helper, icon: Icon, accent = 'cyan' }: MetricCardProps) {
  const displayValue = value ?? val;

  return (
    <div className="rounded-[16px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-4">
      <div className="flex items-center justify-between gap-3 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-secondary)]">
        <span>{label}</span>
        {Icon ? <Icon aria-hidden="true" size={18} className={accentClasses[accent]} /> : null}
      </div>
      <div className="mt-1 text-2xl font-semibold text-[var(--color-text-primary)]">
        {displayValue}
      </div>
      {helper && (
        <div className="mt-1 text-xs text-[var(--color-text-secondary)]">
          {helper}
        </div>
      )}
    </div>
  );
}
