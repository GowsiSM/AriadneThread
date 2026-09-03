export type BadgeVariant = "default" | "danger" | "warning" | "success" | "info" | "neutral";

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-surface-subtle text-fg-secondary border-border",
  danger: "bg-danger/10 text-danger border-danger/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  success: "bg-success/10 text-success border-success/20",
  info: "bg-info/10 text-info border-info/20",
  neutral: "bg-surface-subtle text-fg-muted border-border",
};

export default function StatusBadge({
  children,
  variant = "default",
  dot,
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium ${variantStyles[variant]}`}
    >
      {dot && (
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            variant === "danger"
              ? "bg-danger"
              : variant === "warning"
                ? "bg-warning"
                : variant === "success"
                  ? "bg-success"
                  : variant === "info"
                    ? "bg-info"
                    : "bg-fg-muted"
          }`}
        />
      )}
      {children}
    </span>
  );
}
