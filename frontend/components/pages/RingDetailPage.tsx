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

      {/* Typology & Roles */}
      {ring.typology && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="card p-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-muted">
              Fraud Typology
            </h3>
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-semibold text-fg">
                {ring.typology.replace(/_/g, " ")}
              </span>
              {ring.typology_confidence != null && (
                <span className="text-xs text-fg-muted">
                  ({Math.round(ring.typology_confidence * 100)}% confidence)
                </span>
              )}
            </div>
            {ring.typology === "circular" && (
              <p className="mt-2 text-xs text-fg-muted">
                Money cycles through members back to the originator — classic layering pattern.
              </p>
            )}
          </div>
          {ring.roles && ring.roles.length > 0 && (
            <div className="card p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-muted">
                Role Assignments
              </h3>
              <div className="flex flex-col gap-1.5">
                {ring.roles.map((r) => (
                  <div key={r.user_id} className="flex items-center gap-2 text-xs">
                    <span className="font-mono text-fg">{r.user_id}</span>
                    <span className="text-fg-muted">→</span>
                    <span className="font-medium text-fg-secondary">{r.role.replace(/_/g, " ")}</span>
                    <span className="text-fg-muted">({Math.round(r.confidence * 100)}%)</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Flow Summary */}
      {ring.flow_summary && (
        <div className="card p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Money Flow Summary
          </h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Total inflow</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.total_inflow.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Total outflow</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.total_outflow.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Internal vol.</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.internal_volume.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">External vol.</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.external_volume.toLocaleString("en-IN")}
              </div>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Flow ratio</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{ring.flow_summary.flow_ratio.toFixed(2)}</div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Net flow</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.net_flow.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Concentration</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {(ring.flow_summary.concentration * 100).toFixed(0)}%
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Dominant amount</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {ring.flow_summary.dominant_amount.toLocaleString("en-IN")}
              </div>
            </div>
          </div>
          {ring.flow_summary.dominant_path.length > 0 && (
            <div className="mt-3 rounded-lg bg-surface-subtle p-2.5 text-xs">
              <span className="font-medium text-fg-secondary">Dominant path: </span>
              <span className="font-mono text-fg">
                {ring.flow_summary.dominant_path.join(" → ")}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Motifs */}
      {ring.motifs && ring.motifs.length > 0 && (
        <div className="card p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Detected Motifs
          </h3>
          <div className="flex flex-col gap-2">
            {ring.motifs.map((m, i) => (
              <div key={i} className="rounded-lg border border-border bg-surface-subtle px-3 py-2.5">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-fg">{m.motif_type.replace(/_/g, " ")}</span>
                  <span className="text-fg-muted">({Math.round(m.confidence * 100)}%)</span>
                </div>
                {m.nodes.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {m.nodes.map((n) => (
                      <span key={n} className="font-mono text-[10px] text-fg-secondary">{n}</span>
                    ))}
                  </div>
                )}
                {m.evidence && (
                  <p className="mt-1 text-[11px] text-fg-muted">{m.evidence}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sub-rings */}
      {ring.sub_rings && ring.sub_rings.length > 0 && (
        <div className="card p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Sub-Rings
          </h3>
          <div className="flex flex-col gap-2">
            {ring.sub_rings.map((sr) => (
              <div key={sr.sub_ring_id} className="rounded-lg border border-border bg-surface-subtle px-3 py-2.5">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono font-semibold text-fg">{sr.sub_ring_id}</span>
                  <span className="text-fg-muted">risk contribution:</span>
                  <span className="font-mono text-fg-secondary">{Math.round(sr.risk_contribution * 100)}%</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {sr.members.map((m) => (
                    <span key={m} className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-fg-secondary">{m}</span>
                  ))}
                </div>
                {sr.reason && (
                  <p className="mt-1 text-[11px] text-fg-muted">{sr.reason}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

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
