"use client";

import type { Metrics } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import { EmptyState } from "@/components/States";

export default function MetricsPage({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Detection Metrics"
          description="Performance metrics for the fraud detection pipeline."
        />
        <EmptyState
          icon="⊿"
          title="No metrics available"
          description="Waiting for detection data to populate."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Detection Metrics"
        description="Performance metrics for the fraud detection pipeline."
      />

      {/* Primary Metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Precision"
          value={`${(metrics.precision * 100).toFixed(1)}%`}
          variant={metrics.precision >= 0.9 ? "success" : metrics.precision >= 0.7 ? "warning" : "danger"}
          detail="true positives / flagged"
        />
        <MetricCard
          label="Recall"
          value={`${(metrics.recall * 100).toFixed(1)}%`}
          variant={metrics.recall >= 0.5 ? "success" : metrics.recall >= 0.3 ? "warning" : "danger"}
          detail="true positives / actual"
        />
        <MetricCard
          label="F1 Score"
          value={`${(metrics.f1 * 100).toFixed(1)}%`}
          variant={metrics.f1 >= 0.6 ? "success" : metrics.f1 >= 0.4 ? "warning" : "danger"}
          detail="harmonic mean"
        />
        <MetricCard
          label="Threshold"
          value={metrics.threshold}
          detail="risk score cutoff"
        />
      </div>

      {/* Detailed Metrics */}
      <div className="card overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-fg">Detailed Breakdown</h2>
        </div>
        <div className="p-4">
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b border-border-subtle">
                <td className="py-3 text-fg-muted">True Positives</td>
                <td className="py-3 text-right font-mono font-semibold text-fg">
                  {metrics.true_positive_users}
                </td>
                <td className="py-3 text-right text-xs text-fg-muted">correctly flagged accounts</td>
              </tr>
              <tr className="border-b border-border-subtle">
                <td className="py-3 text-fg-muted">False Positives</td>
                <td className="py-3 text-right font-mono font-semibold text-danger">
                  {metrics.false_positive_users}
                </td>
                <td className="py-3 text-right text-xs text-fg-muted">incorrectly flagged accounts</td>
              </tr>
              <tr className="border-b border-border-subtle">
                <td className="py-3 text-fg-muted">False Negatives</td>
                <td className="py-3 text-right font-mono font-semibold text-warning">
                  {metrics.false_negative_users}
                </td>
                <td className="py-3 text-right text-xs text-fg-muted">missed fraud accounts</td>
              </tr>
              <tr>
                <td className="py-3 text-fg-muted">Detection Threshold</td>
                <td className="py-3 text-right font-mono font-semibold text-fg">
                  {metrics.threshold}
                </td>
                <td className="py-3 text-right text-xs text-fg-muted">minimum ring score to alert</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Metric Bars */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Score Distribution
        </h3>
        <div className="flex flex-col gap-4">
          {[
            { label: "Precision", value: metrics.precision, color: "bg-success" },
            { label: "Recall", value: metrics.recall, color: "bg-info" },
            { label: "F1 Score", value: metrics.f1, color: "bg-accent" },
          ].map((m) => (
            <div key={m.label}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-fg-secondary">{m.label}</span>
                <span className="font-mono text-fg-muted">{(m.value * 100).toFixed(1)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-signal-bar-bg">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${m.color}`}
                  style={{ width: `${m.value * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
