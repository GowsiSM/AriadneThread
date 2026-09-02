"use client";

import type { RingAlert } from "@/lib/types";
import RiskBadge from "./RiskBadge";

export default function AlertsPanel({
  alerts,
  selected,
  onSelect,
}: {
  alerts: RingAlert[];
  selected: string | null;
  onSelect: (ringId: string) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-fg">Detected Rings</h2>
        <span className="font-mono text-[11px] text-fg-muted">{alerts.length} active</span>
      </div>
      <div className="flex max-h-[420px] flex-col overflow-y-auto">
        {alerts.length === 0 && (
          <div className="py-12 text-center text-xs text-fg-muted">
            No rings flagged — watching the stream…
          </div>
        )}
        {alerts.map((a) => (
          <button
            key={a.ring.ring_id}
            onClick={() => onSelect(a.ring.ring_id)}
            className={`flex items-center justify-between border-b border-border-subtle px-4 py-3 text-left transition-colors hover:bg-surface-hover ${
              selected === a.ring.ring_id ? "bg-surface-subtle" : ""
            }`}
          >
            <div className="flex flex-col gap-0.5">
              <span className="font-mono text-xs font-medium text-fg">{a.ring.ring_id}</span>
              <span className="text-[11px] text-fg-muted">
                {a.ring.members.length} members · {(a.ring.score * 0.01).toFixed(1)} score
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-fg">{a.ring.score.toFixed(1)}</span>
              <RiskBadge score={a.ring.score} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
