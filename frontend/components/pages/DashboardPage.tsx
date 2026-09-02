"use client";

import { useState } from "react";
import type { RingAlert, Metrics, CohortStat, TxMessage, StreamStats } from "@/lib/types";
import type { ConnectionState } from "@/lib/useSentinelSocket";
import { PageHeader } from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import GraphView from "@/components/GraphView";
import AlertsPanel from "@/components/AlertsPanel";
import RingDetail from "@/components/RingDetail";
import FairnessPanel from "@/components/FairnessPanel";

export default function DashboardPage({
  alerts,
  metrics,
  cohorts,
  recentTx,
  connectionState,
  streamStats,
}: {
  alerts: RingAlert[];
  metrics: Metrics | null;
  cohorts: CohortStat[];
  recentTx: TxMessage[];
  connectionState: ConnectionState;
  streamStats: StreamStats | null;
}) {
  const [selectedRingId, setSelectedRingId] = useState<string | null>(null);
  const selectedAlert = alerts.find((a) => a.ring.ring_id === selectedRingId) ?? alerts[0] ?? null;

  const highRiskCount = alerts.filter((a) => a.ring.score >= 80).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        description="Monitor suspicious transaction rings and investigation signals."
      />

      {/* Metrics Row */}
      {metrics && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="Detected Rings" value={alerts.length} detail="active rings" />
          <MetricCard
            label="High Risk"
            value={highRiskCount}
            variant={highRiskCount > 0 ? "danger" : "default"}
            detail="score ≥ 80"
          />
          <MetricCard
            label="Precision"
            value={`${(metrics.precision * 100).toFixed(1)}%`}
            variant={metrics.precision >= 0.9 ? "success" : "warning"}
          />
          <MetricCard
            label="Recall"
            value={`${(metrics.recall * 100).toFixed(1)}%`}
            variant={metrics.recall >= 0.5 ? "success" : "warning"}
          />
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="flex flex-col gap-4 lg:col-span-7">
          <GraphView recentTx={recentTx} alerts={alerts} />
          <FairnessPanel cohorts={cohorts} />
        </div>
        <div className="flex flex-col gap-4 lg:col-span-5">
          <AlertsPanel
            alerts={alerts}
            selected={selectedAlert?.ring.ring_id ?? null}
            onSelect={setSelectedRingId}
          />
          <RingDetail alert={selectedAlert} />
        </div>
      </div>
    </div>
  );
}
