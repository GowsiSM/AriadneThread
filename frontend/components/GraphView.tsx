"use client";

import { useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
  type Simulation,
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
  const [nodes, setNodes] = useState<GNode[]>([]);
  const [links, setLinks] = useState<GLink[]>([]);
  const simRef = useRef<Simulation<GNode, GLink> | null>(null);
  const nodesRef = useRef<Map<string, GNode>>(new Map());
  const linksRef = useRef<Map<string, GLink>>(new Map());

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

    if (!simRef.current) {
      simRef.current = forceSimulation<GNode>(nodeArr)
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
        .alpha(0.6)
        .on("tick", () => {
          setNodes([...nodeArr]);
          setLinks([...linkArr]);
        });
    } else {
      simRef.current.nodes(nodeArr);
      (simRef.current.force("link") as ReturnType<typeof forceLink<GNode, GLink>>).links(linkArr);
      simRef.current.alpha(0.5).restart();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentTx, alerts]);

  useEffect(() => {
    return () => {
      simRef.current?.stop();
    };
  }, []);

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-fg">Live transaction graph</h2>
        <span className="font-mono text-[11px] text-fg-muted">
          {nodes.length} nodes · {links.length} edges · cap {MAX_NODES}
        </span>
      </div>
      <div className="bg-graph-bg">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[400px] w-full">
          <g>
            {links.map((l) => {
              const s = l.source as GNode;
              const t = l.target as GNode;
              if (typeof s !== "object" || typeof t !== "object" || s.x == null || t.x == null) return null;
              return (
                <line
                  key={l.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  className={s.flagged || t.flagged ? "stroke-ring-link-flagged" : "stroke-ring-link"}
                  strokeWidth={s.flagged || t.flagged ? 1.2 : 0.6}
                  opacity={0.6}
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
                      r={10}
                      fill="var(--ring-node-glow)"
                    />
                  )}
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={n.flagged ? 5 : 3}
                    className={n.flagged ? "fill-ring-node-flagged" : "fill-ring-node"}
                    stroke={n.flagged ? "var(--foreground)" : "none"}
                    strokeWidth={n.flagged ? 0.8 : 0}
                    opacity={n.flagged ? 1 : 0.7}
                  >
                    <title>{n.id}</title>
                  </circle>
                </g>
              )
            )}
          </g>
        </svg>
      </div>
      <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-fg-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-ring-node-flagged" /> Flagged
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-ring-node" /> Normal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-ring-link-flagged" /> Ring edge
        </span>
      </div>
    </div>
  );
}
