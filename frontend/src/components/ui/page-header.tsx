interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  children?: React.ReactNode;
}

export function PageHeader({ eyebrow, title, children }: PageHeaderProps) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <div className="text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-cyan)]">
          {eyebrow}
        </div>
      )}
      <div className="mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
          {title}
        </h1>
        {children}
      </div>
    </div>
  );
}
