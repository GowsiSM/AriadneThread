"use client";

import AppShell from "@/components/AppShell";
import PageRouter from "@/components/PageRouter";
import SentinelDataProvider, { useSentinelData } from "@/lib/SentinelDataProvider";

function AppContent() {
  const { connectionState, metrics, streamStats } = useSentinelData();

  return (
    <AppShell
      connectionState={connectionState}
      metrics={metrics}
      streamStats={streamStats}
    >
      <PageRouter />
    </AppShell>
  );
}

export default function CatchAllPage() {
  return (
    <SentinelDataProvider>
      <AppContent />
    </SentinelDataProvider>
  );
}
