"use client";

import type { CohortStat } from "@/lib/types";

export default function FairnessPanel({ cohorts }: { cohorts: CohortStat[] }) {
  const maxCost = Math.max(1, ...cohorts.map((c) => c.estimated_cost_inr));

  return (
    <div className="card overflow-hidden">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-fg">Fairness Audit</h2>
        <p className="mt-0.5 text-xs text-fg-muted">
          Segmented false-positive cost by customer cohort
        </p>
      </div>
      <div className="p-4">
        {cohorts.length === 0 && (
          <p className="py-6 text-center text-xs text-fg-muted">
            Waiting for first detection pass…
          </p>
        )}
        {cohorts.length > 0 && (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left text-fg-muted">
                <th className="pb-2 font-medium">Cohort</th>
                <th className="pb-2 text-right font-medium">Users</th>
                <th className="pb-2 text-right font-medium">Flagged</th>
                <th className="pb-2 text-right font-medium">FP</th>
                <th className="pb-2 text-right font-medium">FP Rate</th>
                <th className="pb-2 text-right font-medium">Cost (₹)</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((c) => (
                <tr key={c.cohort} className="border-b border-border-subtle hover:bg-surface-hover">
                  <td className="py-2.5 font-medium text-fg">
                    {c.cohort.replace(/_/g, " ")}
                  </td>
                  <td className="py-2.5 text-right font-mono text-fg-secondary">{c.total_users}</td>
                  <td className="py-2.5 text-right font-mono text-fg-secondary">{c.flagged_users}</td>
                  <td className="py-2.5 text-right font-mono text-fg-secondary">{c.false_positives}</td>
                  <td className="py-2.5 text-right">
                    <span className={`font-mono ${
                      c.fp_rate === 0
                        ? "text-success"
                        : c.fp_rate < 0.05
                          ? "text-warning"
                          : "text-danger"
                    }`}>
                      {(c.fp_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2.5 text-right font-mono text-fg-secondary">
                    ₹{c.estimated_cost_inr.toLocaleString("en-IN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cohorts.length > 0 && (
          <div className="mt-4 flex flex-col gap-2">
            {cohorts.map((c) => (
              <div key={c.cohort} className="flex items-center gap-3">
                <span className="w-32 shrink-0 truncate text-[11px] text-fg-muted">
                  {c.cohort.replace(/_/g, " ")}
                </span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-signal-bar-bg">
                  <div
                    className="h-full rounded-full bg-warning transition-all duration-300"
                    style={{ width: `${(c.estimated_cost_inr / maxCost) * 100}%` }}
                  />
                </div>
                <span className="w-16 text-right font-mono text-[11px] text-fg-muted">
                  ₹{c.estimated_cost_inr.toLocaleString("en-IN")}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
