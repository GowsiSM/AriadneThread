export default function MetricCard({
  label,
  value,
  suffix,
  detail,
  variant = "default",
}: {
  label: string;
  value: string | number;
  suffix?: string;
  detail?: string;
  variant?: "default" | "danger" | "success" | "warning";
}) {
  const colorMap: Record<string, string> = {
    default: "text-fg",
    danger: "text-danger",
    success: "text-success",
    warning: "text-warning",
  };

  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-fg-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={`text-xl font-semibold tabular-nums ${colorMap[variant]}`}>{value}</span>
        {suffix && <span className="text-xs text-fg-muted">{suffix}</span>}
      </div>
      {detail && <div className="mt-0.5 text-[11px] text-fg-muted">{detail}</div>}
    </div>
  );
}
