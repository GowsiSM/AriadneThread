"use client";

import AppShell from "@/components/AppShell";
import PageRouter from "@/components/PageRouter";
import SentinelDataProvider, { useSentinelData } from "@/lib/SentinelDataProvider";

function AppContent() {
  const { connectionState, metrics, streamStats, restartStream } = useSentinelData();

  return (
    <AppShell
      connectionState={connectionState}
      metrics={metrics}
      streamStats={streamStats}
      onRestart={restartStream}
    >
      <PageRouter />
    </AppShell>
  );
}

export default function Home() {
  return (
    <SentinelDataProvider>
      <AppContent />
    </SentinelDataProvider>
  );
}
