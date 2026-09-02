"use client";

import type { Metrics, StreamStats } from "@/lib/types";
import type { ConnectionState } from "@/lib/useSentinelSocket";

function ConnectionBadge({ state, reconnectCount }: { state: ConnectionState; reconnectCount: number }) {
  const config: Record<ConnectionState, { label: string; cls: string }> = {
    connecting: { label: "Connecting…", cls: "bg-surface-subtle text-fg-muted border-border" },
    open: { label: "Live", cls: "bg-success/10 text-success border-success/20" },
    reconnecting: {
      label: `Reconnecting (${reconnectCount})`,
      cls: "bg-warning/10 text-warning border-warning/20",
    },
    closed: { label: "Disconnected", cls: "bg-danger/10 text-danger border-danger/20" },
  };
  const c = config[state];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${c.cls}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${
        state === "open" ? "bg-success" : state === "reconnecting" || state === "connecting" ? "bg-warning" : "bg-danger"
      }`} />
      {c.label}
    </span>
  );
}

export default function StatusBar({
  connectionState,
  reconnectCount,
  metrics,
  streamStats,
}: {
  connectionState: ConnectionState;
  reconnectCount: number;
  metrics: Metrics | null;
  streamStats: StreamStats | null;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Dashboard</h1>
        <ConnectionBadge state={connectionState} reconnectCount={reconnectCount} />
        {streamStats && (
          <span className="text-xs text-fg-muted">
            {streamStats.emitted}/{streamStats.total} txns
            {streamStats.done ? " ✓" : ""}
          </span>
        )}
      </div>
      {metrics && (
        <div className="flex gap-4 text-xs text-fg-muted">
          <span>Precision: <b className="font-mono text-fg">{(metrics.precision * 100).toFixed(1)}%</b></span>
          <span>Recall: <b className="font-mono text-fg">{(metrics.recall * 100).toFixed(1)}%</b></span>
          <span>F1: <b className="font-mono text-fg">{(metrics.f1 * 100).toFixed(1)}%</b></span>
          <span className="text-fg-muted">θ {metrics.threshold}</span>
        </div>
      )}
    </div>
  );
}
