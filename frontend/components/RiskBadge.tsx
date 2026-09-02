import type { BadgeVariant } from "./StatusBadge";
import StatusBadge from "./StatusBadge";

export function riskLevel(score: number): { label: string; variant: BadgeVariant } {
  if (score >= 80) return { label: "HIGH", variant: "danger" };
  if (score >= 65) return { label: "MEDIUM", variant: "warning" };
  if (score >= 55) return { label: "ELEVATED", variant: "info" };
  return { label: "LOW", variant: "success" };
}

export default function RiskBadge({ score }: { score: number }) {
  const { label, variant } = riskLevel(score);
  return (
    <StatusBadge variant={variant} dot>
      {label}
    </StatusBadge>
  );
}
