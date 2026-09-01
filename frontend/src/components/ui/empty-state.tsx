type EmptyStateProps = {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div
      role="status"
      className="rounded-[24px] border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-tertiary)]"
    >
      {message}
    </div>
  )
}
