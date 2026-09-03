export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-sans text-xl font-bold tracking-tight text-fg">{title}</h1>
        {description && (
          <p className="mt-0.5 font-sans text-xs text-fg-muted">{description}</p>
        )}
      </div>
      {children && <div className="mt-2 flex items-center gap-2 sm:mt-0">{children}</div>}
    </div>
  );
}
