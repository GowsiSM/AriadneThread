"use client";

import Sidebar from "./Sidebar";
import Header from "./Header";
import type { Metrics, StreamStats } from "@/lib/types";
import type { ConnectionState } from "@/lib/useSentinelSocket";

export default function AppShell({
  children,
  connectionState,
  metrics,
  streamStats,
}: {
  children: React.ReactNode;
  connectionState: ConnectionState;
  metrics: Metrics | null;
  streamStats: StreamStats | null;
}) {
  return (
    <div className="flex min-h-screen">
      <Sidebar connectionState={connectionState} />
      <div className="flex flex-1 flex-col md:pl-60">
        <Header
          connectionState={connectionState}
          metrics={metrics}
          streamStats={streamStats}
        />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        <footer className="border-t border-border px-6 py-3 text-center text-[11px] text-fg-muted">
          100% synthetic demo data · defense-only · AI explains, deterministic code decides
        </footer>
      </div>
    </div>
  );
}
