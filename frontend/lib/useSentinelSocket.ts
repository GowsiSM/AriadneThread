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
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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
  const connectIdRef = useRef(0);
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>(() => {});

  const teardown = useCallback(() => {
    if (pendingTimerRef.current) {
      clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    setConnectionState("reconnecting");
    const attempt = attemptRef.current + 1;
    attemptRef.current = attempt;
    setReconnectCount(attempt);
    const delay = Math.min(500 * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
    setTimeout(() => {
      if (mountedRef.current) connectRef.current();
    }, delay);
  }, []);

  const openSocket = useCallback((id: number) => {
    if (!mountedRef.current || id !== connectIdRef.current) return;

    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    setConnectionState((prev) => (prev === "open" ? prev : "connecting"));

    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_URL);
    } catch {
      if (id === connectIdRef.current) scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (id !== connectIdRef.current) return;
      attemptRef.current = 0;
      setConnectionState("open");
    };

    ws.onmessage = (event) => {
      if (id !== connectIdRef.current) return;
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      switch (msg.type) {
        case "snapshot": {
          setMetrics(msg.metrics);
          setCohorts(msg.fairness?.cohorts ?? []);
          setStreamStats(msg.stream);
          if (msg.recent_tx && msg.recent_tx.length > 0) {
            setRecentTx(msg.recent_tx.slice(0, RECENT_TX_BUFFER));
          }
          setAlerts(
            msg.rings
              .filter((r) => r.score >= (msg.metrics?.threshold ?? 40))
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
      if (id !== connectIdRef.current) return;
      if (!mountedRef.current) return;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // Browser fires onclose after onerror — that drives reconnection.
    };
  }, [scheduleReconnect]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    teardown();

    const id = ++connectIdRef.current;

    // Debounce: wait a tick before opening the socket. In React StrictMode the
    // effect runs → cleanup → runs again. The cleanup clears pendingTimerRef,
    // so only the second mount's timer fires and actually creates the socket.
    pendingTimerRef.current = setTimeout(() => {
      pendingTimerRef.current = null;
      openSocket(id);
    }, 0);
  }, [teardown, openSocket]);

  // Keep connectRef in sync so scheduleReconnect can call latest connect.
  // Safe as a render-time ref mutation (no re-render triggered).
  connectRef.current = connect; // eslint-disable-line react-hooks/exhaustive-deps

  const restartStream = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/stream/restart`, { method: "POST" });
    } catch {
      // If the restart call fails, still try to reconnect below.
    }
    setRecentTx([]);
    setAlerts([]);
    teardown();
    attemptRef.current = 0;
    setReconnectCount(0);
    connectRef.current();
  }, [teardown]);

  useEffect(() => {
    mountedRef.current = true;
    connectRef.current();
    return () => {
      mountedRef.current = false;
      teardown();
    };
  }, [teardown]);

  return { connectionState, alerts, metrics, cohorts, streamStats, recentTx, reconnectCount, restartStream };
}
