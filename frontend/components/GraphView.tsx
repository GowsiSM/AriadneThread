"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { TxMessage, RingAlert } from "@/lib/types";

interface GNode extends SimulationNodeDatum {
  id: string;
  flagged: boolean;
}
interface GLink extends SimulationLinkDatum<GNode> {
  id: string;
}

const MAX_NODES = 120;
const WIDTH = 720;
const HEIGHT = 460;

export default function GraphView({
  recentTx,
  alerts,
}: {
  recentTx: TxMessage[];
  alerts: RingAlert[];
}) {
  const router = useRouter();
  const [nodes, setNodes] = useState<GNode[]>([]);
  const [links, setLinks] = useState<GLink[]>([]);
  const nodesRef = useRef<Map<string, GNode>>(new Map());
  const linksRef = useRef<Map<string, GLink>>(new Map());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const flaggedMembers = new Set(alerts.flatMap((a) => a.ring.members));

  useEffect(() => {
    const nMap = nodesRef.current;
    const lMap = linksRef.current;

    for (const tx of recentTx.slice(0, 20)) {
      for (const id of [tx.sender, tx.receiver]) {
        if (!nMap.has(id)) {
          nMap.set(id, { id, flagged: flaggedMembers.has(id), x: Math.random() * WIDTH, y: Math.random() * HEIGHT });
        } else {
          nMap.get(id)!.flagged = flaggedMembers.has(id);
        }
      }
      const linkId = `${tx.sender}->${tx.receiver}`;
      if (!lMap.has(linkId)) {
        lMap.set(linkId, { id: linkId, source: tx.sender, target: tx.receiver });
      }
    }

    if (nMap.size > MAX_NODES) {
      const excess = nMap.size - MAX_NODES;
      const keys = Array.from(nMap.keys()).slice(0, excess);
      keys.forEach((k) => nMap.delete(k));
      for (const [lid, l] of Array.from(lMap.entries())) {
        const s = typeof l.source === "object" ? (l.source as GNode).id : l.source;
        const t = typeof l.target === "object" ? (l.target as GNode).id : l.target;
        if (!nMap.has(s as string) || !nMap.has(t as string)) lMap.delete(lid);
      }
    }

    const nodeArr = Array.from(nMap.values());
    const linkArr = Array.from(lMap.values());

    // Stop any previous timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    // Create simulation but immediately stop it — we drive the tick manually
    // to avoid relying on requestAnimationFrame which may not fire.
    const sim = forceSimulation<GNode>(nodeArr)
      .force("charge", forceManyBody().strength(-60))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide(14))
      .force(
        "link",
        forceLink<GNode, GLink>(linkArr)
          .id((d) => d.id)
          .distance(46)
          .strength(0.25)
      )
      .alpha(0.8)
      .stop();

    // Manually tick the simulation via setInterval, which is more reliable than
    // requestAnimationFrame in SSR/dev environments.
    let tickCount = 0;
    timerRef.current = setInterval(() => {
      if (sim.alpha() < sim.alphaMin() || tickCount > 120) {
        clearInterval(timerRef.current!);
        timerRef.current = null;
        return;
      }
      sim.tick();
      tickCount++;
      setNodes([...nodeArr]);
      setLinks([...linkArr]);
    }, 30);

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentTx, alerts]);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-fg">Live transaction graph</h2>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-fg-muted">
            {nodes.length} nodes · {links.length} edges · cap {MAX_NODES}
          </span>
          <button
            onClick={() => router.push("/graph-analysis")}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-border text-fg-muted transition-colors hover:border-accent hover:text-accent"
            title="Open graph analysis"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 17L17 7" />
              <path d="M7 7h10v10" />
            </svg>
          </button>
        </div>
      </div>
      <div className="bg-graph-bg">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[400px] w-full">
          <g>
            {links.map((l) => {
              const s = l.source as GNode;
              const t = l.target as GNode;
              if (typeof s !== "object" || typeof t !== "object" || s.x == null || t.x == null) return null;
              const flagged = s.flagged || t.flagged;
              return (
                <line
                  key={l.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={flagged ? "var(--ring-link-flagged)" : "var(--ring-link)"}
                  strokeWidth={flagged ? 1.2 : 0.6}
                  opacity={flagged ? 0.8 : 0.4}
                />
              );
            })}
            {nodes.map((n) =>
              n.x == null || n.y == null ? null : (
                <g key={n.id}>
                  {n.flagged && (
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={12}
                      fill="var(--ring-node-glow)"
                    />
                  )}
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={n.flagged ? 6 : 3.5}
                    fill={n.flagged ? "var(--ring-node-flagged)" : "var(--ring-node)"}
                    stroke={n.flagged ? "var(--foreground)" : "none"}
                    strokeWidth={n.flagged ? 1 : 0}
                    opacity={n.flagged ? 1 : 0.75}
                  >
                    <title>{n.id}{n.flagged ? " (flagged)" : ""}</title>
                  </circle>
                </g>
              )
            )}
          </g>
        </svg>
      </div>
      <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-fg-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--ring-node-flagged)" }} /> Flagged
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--ring-node)" }} /> Normal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: "var(--ring-link-flagged)" }} /> Ring edge
        </span>
      </div>
    </div>
  );
}
