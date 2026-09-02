"use client";

import Link from "next/link";
import type { RingAlert } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import RiskBadge from "@/components/RiskBadge";
import { EmptyState } from "@/components/States";

export default function RingsPage({ alerts }: { alerts: RingAlert[] }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Detected Rings"
        description="Suspicious communities identified by graph-based detection."
      />

      {alerts.length === 0 ? (
        <EmptyState
          icon="⬡"
          title="No suspicious rings detected"
          description="Watching the transaction stream for emerging fraud patterns."
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-fg-muted">
                  <th className="px-4 py-3 font-medium">Ring</th>
                  <th className="px-4 py-3 text-right font-medium">Risk Score</th>
                  <th className="px-4 py-3 text-right font-medium">Members</th>
                  <th className="px-4 py-3 font-medium">Primary Signals</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Key Edges</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => {
                  const topSignals = a.ring.signals
                    .sort((x, y) => y.value - x.value)
                    .slice(0, 2)
                    .map((s) => s.name.replace(/_/g, " "));
                  return (
                    <tr
                      key={a.ring.ring_id}
                      className="border-b border-border-subtle transition-colors hover:bg-surface-hover"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/rings/${a.ring.ring_id}`}
                          className="font-mono text-sm font-medium text-accent hover:underline"
                        >
                          {a.ring.ring_id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="font-mono font-semibold text-fg">
                          {a.ring.score.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-fg-secondary">
                        {a.ring.members.length}
                      </td>
                      <td className="px-4 py-3 text-fg-secondary">
                        {topSignals.join(" + ")}
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge score={a.ring.score} />
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-fg-muted">
                        {a.ring.key_edges.length}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
