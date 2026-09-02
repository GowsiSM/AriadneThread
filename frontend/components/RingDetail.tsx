"use client";

import type { RingAlert } from "@/lib/types";
import RiskBadge from "./RiskBadge";
import StatusBadge from "./StatusBadge";
import { EmptyState } from "./States";

export default function RingDetail({ alert }: { alert: RingAlert | null }) {
  if (!alert) {
    return (
      <EmptyState
        icon="⬡"
        title="Select a ring to investigate"
        description="Choose a flagged ring from the list to view signals, AI explanation, and blast radius."
      />
    );
  }

  const { ring, explanation, blast_radius: blast } = alert;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {/* Ring Header */}
      <div className="card p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-mono text-lg font-semibold text-fg">{ring.ring_id}</h3>
              <RiskBadge score={ring.score} />
            </div>
            <p className="mt-0.5 text-xs text-fg-muted">
              High-risk transaction ring · {ring.members.length} members
            </p>
          </div>
          <div className="text-right">
            <div className="font-mono text-2xl font-bold text-fg">{ring.score.toFixed(1)}</div>
            <div className="text-[10px] text-fg-muted">risk score</div>
          </div>
        </div>
        <div className="mt-3 flex gap-4 text-xs text-fg-muted">
          <span>
            <span className="font-mono text-fg">{ring.members.length}</span> members
          </span>
          <span>
            <span className="font-mono text-fg">{ring.key_edges.length}</span> key edges
          </span>
        </div>
      </div>

      {/* AI Explanation */}
      <div className="card p-4">
        <div className="mb-2 flex items-center gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-fg-muted">AI Explanation</h4>
          <StatusBadge variant={explanation.source === "ai" ? "info" : "neutral"}>
            {explanation.source === "ai" ? "AI-generated" : "Template fallback"}
          </StatusBadge>
        </div>
        <p className="text-sm leading-relaxed text-fg-secondary">{explanation.text}</p>
        {explanation.source === "template" && explanation.error && (
          <p className="mt-2 text-[11px] text-fg-muted">AI explainer unavailable — showing signal summary</p>
        )}
      </div>

      {/* Detection Signals */}
      <div className="card p-4">
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Detection Signals
        </h4>
        <div className="flex flex-col gap-2.5">
          {ring.signals.map((s) => (
            <div key={s.name} className="flex items-center gap-3">
              <span className="w-40 shrink-0 text-xs text-fg-secondary">
                {s.name.replace(/_/g, " ")}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-signal-bar-bg">
                <div
                  className="h-full rounded-full bg-signal-bar transition-all duration-300"
                  style={{ width: `${Math.round(s.value * 100)}%` }}
                />
              </div>
              <span className="w-10 text-right font-mono text-xs text-fg-muted">
                {Math.round(s.value * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Blast Radius */}
      <div className="card p-4">
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Blast Radius Assessment
        </h4>
        {blast.total_members > 0 ? (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Innocent accounts</div>
                <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                  {blast.likely_innocent}
                  <span className="text-xs font-normal text-fg-muted"> / {blast.total_members}</span>
                </div>
                <div className="text-[10px] text-fg-muted">{Math.round(blast.innocent_ratio * 100)}% at risk</div>
              </div>
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Value at risk</div>
                <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                  ₹{blast.value_at_risk_inr.toLocaleString("en-IN")}
                </div>
              </div>
            </div>
            {blast.dominant_cohorts.length > 0 && (
              <div className="text-xs text-fg-secondary">
                <span className="text-fg-muted">Dominant cohorts:</span>{" "}
                {blast.dominant_cohorts.join(", ")}
              </div>
            )}
            {blast.recommendation && (
              <div className="rounded-lg border border-border bg-surface-subtle p-3 text-xs leading-relaxed text-fg-secondary">
                {blast.recommendation}
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-fg-muted">Blast radius data loading…</p>
        )}
      </div>
    </div>
  );
}
