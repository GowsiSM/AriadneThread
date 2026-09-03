"use client";

import ThemeToggle from "./ThemeToggle";
import type { Metrics, StreamStats } from "@/lib/types";
import type { ConnectionState } from "@/lib/useSentinelSocket";

export default function Header({
  connectionState,
  metrics,
  streamStats,
  onRestart,
}: {
  connectionState: ConnectionState;
  metrics: Metrics | null;
  streamStats: StreamStats | null;
  onRestart?: () => void;
}) {
  const streamDone = streamStats?.done ?? false;
  const statusDot =
    connectionState === "open"
      ? streamDone
        ? "bg-fg-muted"
        : "bg-success"
      : connectionState === "reconnecting"
        ? "bg-warning"
        : connectionState === "connecting"
          ? "bg-warning animate-pulse"
          : "bg-danger";

  const statusLabel =
    connectionState === "open"
      ? streamDone
        ? "Stream completed"
        : "Stream active"
      : connectionState === "reconnecting"
        ? "Reconnecting…"
        : connectionState === "connecting"
          ? "Connecting…"
          : "Disconnected";

  const pct = streamStats && streamStats.total > 0
    ? Math.round((streamStats.emitted / streamStats.total) * 100)
    : 0;

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-surface/80 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-4">
        <div className="hidden md:block" />
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${statusDot}`} />
          <span className="text-xs text-fg-secondary">{statusLabel}</span>
        </div>
        {streamStats && (
          <div className="hidden items-center gap-2 sm:flex">
            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-signal-bar-bg">
              <div
                className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-fg-muted">
              {streamStats.emitted}/{streamStats.total} txns
              {streamStats.done ? " ✓" : ""}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {metrics && (
          <div className="hidden items-center gap-3 text-xs text-fg-muted lg:flex">
            <span>
              P <span className="font-mono text-fg">{(metrics.precision * 100).toFixed(1)}%</span>
            </span>
            <span className="text-border">|</span>
            <span>
              R <span className="font-mono text-fg">{(metrics.recall * 100).toFixed(1)}%</span>
            </span>
            <span className="text-border">|</span>
            <span>
              F1 <span className="font-mono text-fg">{(metrics.f1 * 100).toFixed(1)}%</span>
            </span>
          </div>
        )}
        {onRestart && (
          <button
            onClick={onRestart}
            className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:border-accent hover:text-accent"
            title="Replay the transaction stream from the beginning"
          >
            ↻ Restart stream
          </button>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
