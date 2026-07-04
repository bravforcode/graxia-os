interface MetricCardProps {
  label: string;
  val: string | number;
  helper?: string;
}

export function MetricCard({ label, val, helper }: MetricCardProps) {
  return (
    <div className="rounded-[16px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-secondary)]">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-[var(--color-text-primary)]">
        {val}
      </div>
      {helper && (
        <div className="mt-1 text-xs text-[var(--color-text-secondary)]">
          {helper}
        </div>
      )}
    </div>
  );
}
