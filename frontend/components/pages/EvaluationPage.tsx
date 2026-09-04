"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { LoadingState, EmptyState } from "@/components/States";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface EvalData {
  threshold_sweep: {
    points: {
      threshold: number;
      precision: number;
      recall: number;
      f1: number;
      tp: number;
      fp: number;
      fn: number;
      tn: number;
    }[];
    optimal_threshold: number;
    best_f1: number;
    pr_auc: number;
    roc_auc: number;
  };
  baselines: {
    name: string;
    precision: number;
    recall: number;
    f1: number;
  }[];
  temporal_split: {
    train_metrics: Record<string, number>;
    test_metrics: Record<string, number>;
    decay_rate: number;
  } | null;
  adversarial: {
    results: {
      variation: string;
      parameter: string;
      original_score: number;
      perturbed_score: number;
      score_drop: number;
      detection_maintained: boolean;
    }[];
    avg_score_drop: number;
    max_score_drop: number;
    worst_evasion: string;
    best_robustness: string;
    pass_rate: number;
  } | null;
  current_threshold: number;
  n_users: number;
  n_transactions: number;
}

function MetricCard({
  label,
  value,
  variant,
}: {
  label: string;
  value: string;
  variant?: "danger" | "warning" | "success" | "info";
}) {
  return (
    <div className="card px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono text-lg font-semibold tabular-nums ${variant ? `text-${variant}` : "text-fg"}`}
      >
        {value}
      </div>
    </div>
  );
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/evaluation`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load evaluation",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading && !data) return <LoadingState cycleMessages />;
  if (error && !data)
    return (
      <EmptyState
        icon="⚠"
        title="Evaluation failed"
        description={error}
        action={
          <button
            onClick={refresh}
            className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
          >
            Retry
          </button>
        }
      />
    );
  if (!data) return null;

  const {
    threshold_sweep: sweep,
    baselines,
    temporal_split,
    adversarial,
  } = data;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Evaluation"
        description="Threshold sweep, baseline comparison, and adversarial robustness"
      >
        <button
          onClick={refresh}
          className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:border-accent hover:text-accent"
        >
          ↻ Re-run
        </button>
      </PageHeader>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="PR-AUC"
          value={sweep.pr_auc.toFixed(3)}
          variant="info"
        />
        <MetricCard
          label="ROC-AUC"
          value={sweep.roc_auc.toFixed(3)}
          variant="info"
        />
        <MetricCard
          label="Best threshold"
          value={sweep.optimal_threshold.toFixed(1)}
        />
        <MetricCard
          label="Adversarial pass rate"
          value={`${(adversarial?.pass_rate ?? 0).toFixed(0)}%`}
          variant={
            adversarial && adversarial.pass_rate >= 0.8 ? "success" : "warning"
          }
        />
      </div>

      {/* Threshold sweep */}
      <div className="card p-4">
        <h3 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Threshold Sweep
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border font-mono text-[11px] uppercase tracking-wider text-fg-muted">
                <th className="px-2 py-1.5 text-left font-medium">Threshold</th>
                <th className="px-2 py-1.5 text-right font-medium">
                  Precision
                </th>
                <th className="px-2 py-1.5 text-right font-medium">Recall</th>
                <th className="px-2 py-1.5 text-right font-medium">F1</th>
                <th className="px-2 py-1.5 text-right font-medium">TP</th>
                <th className="px-2 py-1.5 text-right font-medium">FP</th>
              </tr>
            </thead>
            <tbody>
              {sweep.points.map((r) => {
                const isCurrent =
                  Math.abs(r.threshold - data.current_threshold) < 0.1;
                return (
                  <tr
                    key={r.threshold}
                    className={`border-b border-border ${isCurrent ? "bg-accent/5" : ""}`}
                  >
                    <td className="px-2 py-1.5 font-mono text-fg flex items-center gap-2">
                      {r.threshold.toFixed(1)}
                      {isCurrent && (
                        <StatusBadge variant="info">current</StatusBadge>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.precision.toFixed(3)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.recall.toFixed(3)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.f1.toFixed(3)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.tp}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.fp}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Baselines */}
      <div className="card p-4">
        <h3 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Baseline Comparison
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border font-mono text-[11px] uppercase tracking-wider text-fg-muted">
                <th className="px-2 py-1.5 text-left font-medium">Method</th>
                <th className="px-2 py-1.5 text-right font-medium">
                  Precision
                </th>
                <th className="px-2 py-1.5 text-right font-medium">Recall</th>
                <th className="px-2 py-1.5 text-right font-medium">F1</th>
              </tr>
            </thead>
            <tbody>
              {baselines.map((b, i) => {
                const isGraph =
                  b.name.includes("graph") ||
                  b.name.includes("Graph") ||
                  b.name.includes("Sentinel");
                return (
                  <tr
                    key={i}
                    className={`border-b border-border ${isGraph ? "bg-accent/5" : ""}`}
                  >
                    <td className="px-2 py-1.5 font-mono text-fg flex items-center gap-2">
                      {b.name}
                      {isGraph && (
                        <StatusBadge variant="info">ours</StatusBadge>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {b.precision.toFixed(3)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {b.recall.toFixed(3)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {b.f1.toFixed(3)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Temporal split */}
      {temporal_split && (
        <div className="card p-4">
          <h3 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Temporal Split
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Train F1
              </div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-fg">
                {(temporal_split.train_metrics.f1 ?? 0).toFixed(3)}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Test F1
              </div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-fg">
                {(temporal_split.test_metrics.f1 ?? 0).toFixed(3)}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Decay rate
              </div>
              <div
                className={`mt-0.5 font-mono text-lg font-semibold tabular-nums ${temporal_split.decay_rate < 0.1 ? "text-success" : "text-warning"}`}
              >
                {(temporal_split.decay_rate * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Adversarial robustness */}
      {adversarial && (
        <div className="card p-4">
          <h3 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Adversarial Robustness
          </h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Avg score drop
              </div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-warning">
                {adversarial.avg_score_drop.toFixed(1)}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Max score drop
              </div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-danger">
                {adversarial.max_score_drop.toFixed(1)}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Worst evasion
              </div>
              <div className="mt-0.5 font-mono text-sm text-fg-secondary">
                {adversarial.worst_evasion}
              </div>
            </div>
            <div className="rounded-lg bg-surface-subtle p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                Best robustness
              </div>
              <div className="mt-0.5 font-mono text-sm text-fg-secondary">
                {adversarial.best_robustness}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border font-mono text-[11px] uppercase tracking-wider text-fg-muted">
                  <th className="px-2 py-1.5 text-left font-medium">
                    Variation
                  </th>
                  <th className="px-2 py-1.5 text-right font-medium">
                    Original
                  </th>
                  <th className="px-2 py-1.5 text-right font-medium">
                    Perturbed
                  </th>
                  <th className="px-2 py-1.5 text-right font-medium">Drop</th>
                  <th className="px-2 py-1.5 text-right font-medium">
                    Detected
                  </th>
                </tr>
              </thead>
              <tbody>
                {adversarial.results.map((r) => (
                  <tr key={r.variation} className="border-b border-border">
                    <td className="px-2 py-1.5 text-fg-secondary">
                      {r.variation.replace(/_/g, " ")}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.original_score.toFixed(1)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.perturbed_score.toFixed(1)}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-fg-secondary">
                      {r.score_drop.toFixed(1)}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <StatusBadge
                        variant={r.detection_maintained ? "success" : "danger"}
                        dot
                      >
                        {r.detection_maintained ? "yes" : "no"}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dataset info */}
      <div className="card p-4">
        <h3 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Evaluation Dataset
        </h3>
        <div className="flex gap-4 text-xs text-fg-secondary">
          <span>
            Users: <span className="font-mono text-fg">{data.n_users}</span>
          </span>
          <span>
            Transactions:{" "}
            <span className="font-mono text-fg">{data.n_transactions}</span>
          </span>
          <span>
            Threshold:{" "}
            <span className="font-mono text-fg">{data.current_threshold}</span>
          </span>
          <Link href="/versions" className="text-accent hover:underline">
            → Version details
          </Link>
        </div>
      </div>
    </div>
  );
}
