"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type {
  ServerMessage,
  RingAlert,
  Metrics,
  CohortStat,
  StreamStats,
  TxMessage,
} from "./types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/stream";
const MAX_RECONNECT_DELAY_MS = 8000;
const RECENT_TX_BUFFER = 60;

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export function useSentinelSocket() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [alerts, setAlerts] = useState<RingAlert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [cohorts, setCohorts] = useState<CohortStat[]>([]);
  const [streamStats, setStreamStats] = useState<StreamStats | null>(null);
  const [recentTx, setRecentTx] = useState<TxMessage[]>([]);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    setConnectionState((prev) => (prev === "open" ? prev : "connecting"));

    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_URL);
    } catch (err) {
      // WebSocket constructor can throw synchronously on malformed URLs etc.
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      setConnectionState("open");
    };

    ws.onmessage = (event) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return; // ignore malformed frames rather than crashing the UI
      }
      switch (msg.type) {
        case "snapshot": {
          setMetrics(msg.metrics);
          setCohorts(msg.fairness?.cohorts ?? []);
          setStreamStats(msg.stream);
          setAlerts(
            msg.rings
              .filter((r) => r.score >= (msg.metrics?.threshold ?? 55))
              .map((r) => ({
                ring: r,
                explanation: { text: "(loaded from snapshot)", source: "template", error: null },
                blast_radius: {
                  ring_id: r.ring_id,
                  total_members: r.members.length,
                  likely_innocent: 0,
                  innocent_ratio: 0,
                  txn_volume_last_window: 0,
                  value_at_risk_inr: 0,
                  dominant_cohorts: [],
                  recommendation: "",
                },
                receivedAt: Date.now(),
              }))
          );
          break;
        }
        case "transaction": {
          setRecentTx((prev) => [msg.tx, ...prev].slice(0, RECENT_TX_BUFFER));
          break;
        }
        case "ring_alert": {
          setAlerts((prev) => {
            const filtered = prev.filter((a) => a.ring.ring_id !== msg.ring.ring_id);
            return [
              { ring: msg.ring, explanation: msg.explanation, blast_radius: msg.blast_radius, receivedAt: Date.now() },
              ...filtered,
            ].slice(0, 20);
          });
          break;
        }
        case "metrics_update": {
          setMetrics(msg.metrics);
          setCohorts(msg.fairness?.cohorts ?? []);
          setStreamStats(msg.stream);
          break;
        }
        case "stream_complete": {
          setStreamStats(msg.stream);
          break;
        }
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (!mountedRef.current) return;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will also fire; avoid double scheduling by letting onclose drive it.
      ws.close();
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    setConnectionState("reconnecting");
    const attempt = attemptRef.current + 1;
    attemptRef.current = attempt;
    setReconnectCount(attempt);
    const delay = Math.min(500 * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
    setTimeout(() => {
      if (mountedRef.current) connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
    };
  }, [connect]);

  return { connectionState, alerts, metrics, cohorts, streamStats, recentTx, reconnectCount };
}
