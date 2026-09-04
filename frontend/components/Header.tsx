"use client";

import ThemeToggle from "./ThemeToggle";
import type { Metrics, StreamStats } from "@/lib/types";

export default function Header({
  metrics,
  streamStats,
  onRestart,
}: {
  metrics: Metrics | null;
  streamStats: StreamStats | null;
  onRestart?: () => void;
}) {
  const streamDone = streamStats?.done ?? false;

  const pct =
    streamStats && streamStats.total > 0
      ? Math.round((streamStats.emitted / streamStats.total) * 100)
      : 0;

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-surface/80 px-6 backdrop-blur-sm">
      {/* Left: progress bar */}
      {streamStats && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-signal-bar-bg">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="whitespace-nowrap font-mono text-xs tabular-nums text-fg-muted">
            {streamStats.emitted}/{streamStats.total} txns
            {streamStats.done ? " ✓" : ""}
          </span>
        </div>
      )}

      {/* Right: metric badges + restart + theme */}
      <div className="flex shrink-0 items-center gap-3">
        {metrics && (
          <div className="hidden items-center gap-2 sm:flex">
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-subtle px-2 py-1 font-mono text-xs font-medium text-fg-muted">
              P{" "}
              <span className="font-semibold tabular-nums text-fg">
                {(metrics.precision * 100).toFixed(1)}%
              </span>
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-subtle px-2 py-1 font-mono text-xs font-medium text-fg-muted">
              R{" "}
              <span className="font-semibold tabular-nums text-fg">
                {(metrics.recall * 100).toFixed(1)}%
              </span>
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-subtle px-2 py-1 font-mono text-xs font-medium text-fg-muted">
              F1{" "}
              <span className="font-semibold tabular-nums text-fg">
                {(metrics.f1 * 100).toFixed(1)}%
              </span>
            </span>
          </div>
        )}
        {onRestart && (
          <button
            onClick={onRestart}
            className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 font-sans text-sm font-medium text-fg transition-colors hover:border-accent hover:text-accent"
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
