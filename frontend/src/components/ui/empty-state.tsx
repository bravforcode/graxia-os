interface EmptyStateProps {
  msg: string;
}

export function EmptyState({ msg }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[16px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-12 text-center">
      <p className="text-sm text-[var(--color-text-secondary)]">{msg}</p>
    </div>
  );
}
