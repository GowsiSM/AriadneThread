"use client";

import type { TxMessage, RingAlert } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import GraphAnalysisView from "@/components/GraphAnalysisView";

export default function GraphAnalysisPage({
  recentTx,
  alerts,
}: {
  recentTx: TxMessage[];
  alerts: RingAlert[];
}) {
  return (
    <div className="flex flex-1 flex-col gap-4 overflow-hidden" style={{ height: "calc(100vh - 3.5rem)" }}>
      <PageHeader
        title="Graph Analysis"
        description="Interactive zoomable view of the full transaction network. Scroll to zoom, drag to pan."
      />
      <GraphAnalysisView recentTx={recentTx} alerts={alerts} />
    </div>
  );
}
