"use client";

import type { CohortStat } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import FairnessPanel from "@/components/FairnessPanel";
import { EmptyState } from "@/components/States";

export default function FairnessPage({ cohorts }: { cohorts: CohortStat[] }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Fairness Audit"
        description="Monitor false-positive rates across user cohorts to detect demographic disparities."
      />

      {cohorts.length === 0 ? (
        <EmptyState
          icon="⊞"
          title="No fairness data yet"
          description="Waiting for the first detection pass to complete."
        />
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="card px-4 py-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Total Cohorts</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">{cohorts.length}</div>
            </div>
            <div className="card px-4 py-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Total FP</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {cohorts.reduce((sum, c) => sum + c.false_positives, 0)}
              </div>
            </div>
            <div className="card px-4 py-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Avg FP Rate</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {(
                  (cohorts.reduce((sum, c) => sum + c.fp_rate, 0) / cohorts.length) *
                  100
                ).toFixed(1)}
                %
              </div>
            </div>
            <div className="card px-4 py-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">Total Cost</div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-danger">
                ₹{cohorts.reduce((sum, c) => sum + c.estimated_cost_inr, 0).toLocaleString("en-IN")}
              </div>
            </div>
          </div>

          <FairnessPanel cohorts={cohorts} />
        </>
      )}
    </div>
  );
}
