"use client";

import Link from "next/link";
import type { RingAlert } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import RiskBadge from "@/components/RiskBadge";
import StatusBadge from "@/components/StatusBadge";
import { EmptyState } from "@/components/States";
import { useSentinelData } from "@/lib/SentinelDataProvider";

export default function RingDetailPage({ ringId }: { ringId: string }) {
  const { alerts } = useSentinelData();
  const alert = alerts.find((a) => a.ring.ring_id === ringId);

  if (!alert) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={ringId} description="Ring investigation" />
        <EmptyState
          icon="⬡"
          title={`Ring ${ringId} not found`}
          description="This ring may not have been detected yet, or the ID may be incorrect."
          action={
            <Link
              href="/rings"
              className="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover"
            >
              ← Back to rings
            </Link>
          }
        />
      </div>
    );
  }

  const { ring, explanation, blast_radius: blast } = alert;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/rings"
          className="mb-2 inline-flex items-center gap-1 text-xs text-fg-muted transition-colors hover:text-fg"
        >
          ← Detected Rings
        </Link>
        <PageHeader
          title={ring.ring_id}
          description="High-risk transaction ring — investigation workspace"
        >
          <div className="flex items-center gap-3">
            <RiskBadge score={ring.score} />
            <span className="font-mono text-2xl font-bold text-fg">{ring.score.toFixed(1)}</span>
          </div>
        </PageHeader>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="card px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted">Members</div>
          <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{ring.members.length}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted">Key Edges</div>
          <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{ring.key_edges.length}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted">Signals</div>
          <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{ring.signals.length}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-fg-muted">Risk Score</div>
          <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{ring.score.toFixed(1)}/100</div>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left: Members & Edges */}
        <div className="card p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Ring Members
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {ring.members.map((m) => (
              <span
                key={m}
                className="inline-flex items-center rounded-md border border-border bg-surface-subtle px-2 py-1 font-mono text-[11px] text-fg-secondary"
              >
                {m}
              </span>
            ))}
          </div>
          {ring.key_edges.length > 0 && (
            <>
              <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-fg-muted">
                Key Edges
              </h3>
              <div className="flex flex-col gap-1">
                {ring.key_edges.map(([from, to], i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 font-mono text-[11px] text-fg-secondary"
                  >
                    <span>{from}</span>
                    <span className="text-fg-muted">→</span>
                    <span>{to}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Right: AI Explanation */}
        <div className="card p-4">
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-muted">AI Explanation</h3>
            <StatusBadge variant={explanation.source === "ai" ? "info" : "neutral"}>
              {explanation.source === "ai" ? "AI-generated" : "Template"}
            </StatusBadge>
          </div>
          <p className="text-sm leading-relaxed text-fg-secondary">{explanation.text}</p>
          {explanation.source === "template" && explanation.error && (
            <p className="mt-2 text-[11px] text-fg-muted">
              AI explainer unavailable — showing signal summary
            </p>
          )}
        </div>
      </div>

      {/* Detection Signals */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Detection Signals
        </h3>
        <div className="flex flex-col gap-3">
          {ring.signals.map((s) => (
            <div key={s.name} className="flex items-center gap-3">
              <span className="w-44 shrink-0 text-xs text-fg-secondary">
                {s.name.replace(/_/g, " ")}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-signal-bar-bg">
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
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Blast Radius Assessment
        </h3>
        {blast.total_members > 0 ? (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Innocent caught</div>
                <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                  {blast.likely_innocent}
                  <span className="text-xs font-normal text-fg-muted"> / {blast.total_members}</span>
                </div>
              </div>
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Value at risk</div>
                <div className="mt-0.5 font-mono text-lg font-semibold text-danger">
                  ₹{blast.value_at_risk_inr.toLocaleString("en-IN")}
                </div>
              </div>
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Innocent ratio</div>
                <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                  {Math.round(blast.innocent_ratio * 100)}%
                </div>
              </div>
              <div className="rounded-lg bg-surface-subtle p-3">
                <div className="text-[10px] uppercase tracking-wider text-fg-muted">Dominant cohorts</div>
                <div className="mt-0.5 text-sm text-fg-secondary">
                  {blast.dominant_cohorts.join(", ") || "—"}
                </div>
              </div>
            </div>
            {blast.recommendation && (
              <div className="rounded-lg border border-border bg-surface-subtle p-3 text-xs leading-relaxed text-fg-secondary">
                <span className="font-medium text-fg">Recommendation:</span> {blast.recommendation}
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
