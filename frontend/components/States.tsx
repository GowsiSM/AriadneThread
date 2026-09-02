export function EmptyState({
  icon = "○",
  title,
  description,
  action,
}: {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <span className="mb-3 text-2xl text-fg-muted">{icon}</span>
      <p className="text-sm font-medium text-fg-secondary">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-fg-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-3 h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent" />
      <p className="text-xs text-fg-muted">{message}</p>
    </div>
  );
}
