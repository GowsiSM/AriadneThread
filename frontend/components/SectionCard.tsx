export default function SectionCard({
  title,
  description,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`card ${className}`}>
      {(title || description) && (
        <div className="border-b border-border px-4 py-3">
          {title && <h2 className="text-sm font-semibold text-fg">{title}</h2>}
          {description && <p className="mt-0.5 text-xs text-fg-muted">{description}</p>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
