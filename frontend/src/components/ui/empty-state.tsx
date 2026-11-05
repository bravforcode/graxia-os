type EmptyStateProps =
  | { message: string; msg?: string }
  | { msg: string; message?: string };

export function EmptyState({ message, msg }: EmptyStateProps) {
  const text = message ?? msg;

  return (
    <div role="status" className="flex flex-col items-center justify-center rounded-[16px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-12 text-center">
      <p className="text-sm text-[var(--color-text-secondary)]">{text}</p>
    </div>
  );
}
