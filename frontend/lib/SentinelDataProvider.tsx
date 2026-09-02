"use client";

import { createContext, useContext } from "react";
import { useSentinelSocket, type ConnectionState } from "@/lib/useSentinelSocket";
import type { RingAlert, Metrics, CohortStat, StreamStats, TxMessage } from "@/lib/types";

interface SentinelData {
  connectionState: ConnectionState;
  reconnectCount: number;
  alerts: RingAlert[];
  metrics: Metrics | null;
  cohorts: CohortStat[];
  streamStats: StreamStats | null;
  recentTx: TxMessage[];
}

const SentinelContext = createContext<SentinelData>({
  connectionState: "connecting",
  reconnectCount: 0,
  alerts: [],
  metrics: null,
  cohorts: [],
  streamStats: null,
  recentTx: [],
});

export function useSentinelData() {
  return useContext(SentinelContext);
}

export default function SentinelDataProvider({ children }: { children: React.ReactNode }) {
  const data = useSentinelSocket();
  return (
    <SentinelContext.Provider value={data}>
      {children}
    </SentinelContext.Provider>
  );
}
