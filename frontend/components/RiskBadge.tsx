import type { BadgeVariant } from "./StatusBadge";
import StatusBadge from "./StatusBadge";

export function riskLevel(score: number): {
  label: string;
  variant: BadgeVariant;
} {
  if (score >= 80) return { label: "HIGH", variant: "danger" };
  if (score >= 65) return { label: "MEDIUM", variant: "warning" };
  // 40 matches SCORE_THRESHOLD in backend/app/main.py -- anything at or
  // above this is an actively flagged ring, so it should never render as
  // "LOW" even at the bottom of the flagged range.
  if (score >= 40) return { label: "ELEVATED", variant: "info" };
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
