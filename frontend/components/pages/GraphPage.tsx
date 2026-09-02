"use client";

import type { TxMessage, RingAlert } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import GraphView from "@/components/GraphView";

export default function GraphPage({
  recentTx,
  alerts,
}: {
  recentTx: TxMessage[];
  alerts: RingAlert[];
}) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Graph Analysis"
        description="Interactive visualization of the transaction network and flagged rings."
      />
      <GraphView recentTx={recentTx} alerts={alerts} />
    </div>
  );
}
