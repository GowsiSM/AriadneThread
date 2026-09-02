"use client";

import ThemeToggle from "./ThemeToggle";
import type { Metrics, StreamStats } from "@/lib/types";
import type { ConnectionState } from "@/lib/useSentinelSocket";

export default function Header({
  connectionState,
  metrics,
  streamStats,
}: {
  connectionState: ConnectionState;
  metrics: Metrics | null;
  streamStats: StreamStats | null;
}) {
  const statusDot =
    connectionState === "open"
      ? "bg-success"
      : connectionState === "reconnecting"
        ? "bg-warning"
        : connectionState === "connecting"
          ? "bg-warning animate-pulse"
          : "bg-danger";

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-surface/80 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-4">
        <div className="hidden md:block" />
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${statusDot}`} />
          <span className="text-xs text-fg-secondary">
            {connectionState === "open" ? "Stream active" : connectionState === "reconnecting" ? "Reconnecting…" : connectionState === "connecting" ? "Connecting…" : "Disconnected"}
          </span>
        </div>
        {streamStats && (
          <span className="hidden text-xs text-fg-muted sm:inline">
            {streamStats.emitted}/{streamStats.total} txns
            {streamStats.done ? " ✓" : ""}
          </span>
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
        <ThemeToggle />
      </div>
    </header>
  );
}
