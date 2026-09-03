"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { select } from "d3-selection";
import type { TxMessage, RingAlert } from "@/lib/types";

interface GNode extends SimulationNodeDatum {
  id: string;
  flagged: boolean;
}
interface GLink extends SimulationLinkDatum<GNode> {
  id: string;
}

const MAX_NODES = 200; // More nodes allowed in full analysis view
const WIDTH = 1200;
const HEIGHT = 800;
const PADDING = 60;

export default function GraphAnalysisView({
  recentTx,
  alerts,
}: {
  recentTx: TxMessage[];
  alerts: RingAlert[];
}) {
  const [nodes, setNodes] = useState<GNode[]>([]);
  const [links, setLinks] = useState<GLink[]>([]);
  const nodesRef = useRef<Map<string, GNode>>(new Map());
  const linksRef = useRef<Map<string, GLink>>(new Map());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Zoom/pan state — stored in refs for performance, synced to React sparingly
  const svgRef = useRef<SVGSVGElement>(null);
  const gRef = useRef<SVGGElement>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const transformRef = useRef<ZoomTransform>(zoomIdentity);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [transformStr, setTransformStr] = useState<string>(zoomIdentity.toString());

  // Node drag state — refs to avoid re-renders during drag
  const dragRef = useRef<{ node: GNode | null; startX: number; startY: number }>({
    node: null,
    startX: 0,
    startY: 0,
  });

  const flaggedMembers = new Set(alerts.flatMap((a) => a.ring.members));

  // --- Force simulation (same as GraphView but with more nodes) ---
  useEffect(() => {
    const nMap = nodesRef.current;
    const lMap = linksRef.current;

    for (const tx of recentTx.slice(0, 30)) {
      for (const id of [tx.sender, tx.receiver]) {
        if (!nMap.has(id)) {
          nMap.set(id, {
            id,
            flagged: flaggedMembers.has(id),
            x: Math.random() * WIDTH,
            y: Math.random() * HEIGHT,
          });
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

    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    const sim = forceSimulation<GNode>(nodeArr)
      .force("charge", forceManyBody().strength(-80))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide(16))
      .force(
        "link",
        forceLink<GNode, GLink>(linkArr)
          .id((d) => d.id)
          .distance(50)
          .strength(0.2)
      )
      .alpha(0.8)
      .stop();

    let tickCount = 0;
    timerRef.current = setInterval(() => {
      if (sim.alpha() < sim.alphaMin() || tickCount > 150) {
        clearInterval(timerRef.current!);
        timerRef.current = null;
        return;
      }
      sim.tick();
      tickCount++;
      setNodes([...nodeArr]);
      setLinks([...linkArr]);
    }, 30);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [recentTx, alerts]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- D3 Zoom setup ---
  useEffect(() => {
    if (!svgRef.current) return;

    const svg = select(svgRef.current);

    const zoomed = (event: { transform: ZoomTransform }) => {
      transformRef.current = event.transform;
      setTransformStr(event.transform.toString());
      setZoomLevel(Math.round(event.transform.k * 100));
    };

    const behavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 8])
      .on("zoom", zoomed);

    svg.call(behavior);
    zoomBehaviorRef.current = behavior;

    return () => {
      svg.on(".zoom", null);
    };
  }, []);

  // --- Zoom/pan control handlers ---
  const handleZoomIn = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    zoomBehaviorRef.current.scaleBy(select(svgRef.current), 1.4);
  }, []);

  const handleZoomOut = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    zoomBehaviorRef.current.scaleBy(select(svgRef.current), 0.7);
  }, []);

  const handleFitToGraph = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current || nodes.length === 0) return;

    const svgEl = svgRef.current;
    const bbox = svgEl.getBoundingClientRect();
    const svgWidth = bbox.width || WIDTH;
    const svgHeight = bbox.height || HEIGHT;

    // Calculate bounding box of all nodes
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      if (n.x == null || n.y == null) continue;
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    }

    if (minX === Infinity) return; // No valid nodes

    const graphWidth = maxX - minX || 1;
    const graphHeight = maxY - minY || 1;
    const graphCx = (minX + maxX) / 2;
    const graphCy = (minY + maxY) / 2;

    const scaleX = (svgWidth - PADDING * 2) / graphWidth;
    const scaleY = (svgHeight - PADDING * 2) / graphHeight;
    const scale = Math.min(scaleX, scaleY, 3); // Cap at 3x

    const tx = svgWidth / 2 - graphCx * scale;
    const ty = svgHeight / 2 - graphCy * scale;

    const t = zoomIdentity.translate(tx, ty).scale(scale);

    zoomBehaviorRef.current.transform(select(svgRef.current), t);
  }, [nodes]);

  const handleReset = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    zoomBehaviorRef.current.transform(select(svgRef.current), zoomIdentity);
  }, []);

  // --- Node drag (pointer events on nodes, not on SVG) ---
  const handleNodePointerDown = useCallback(
    (e: React.PointerEvent, node: GNode) => {
      e.stopPropagation(); // Don't trigger zoom/pan
      (e.target as Element).setPointerCapture(e.pointerId);
      dragRef.current = { node, startX: e.clientX, startY: e.clientY };
    },
    []
  );

  const handleNodePointerMove = useCallback(
    (e: React.PointerEvent) => {
      const d = dragRef.current.node;
      if (!d || !svgRef.current) return;

      const svgEl = svgRef.current;
      const bbox = svgEl.getBoundingClientRect();
      const svgWidth = bbox.width || WIDTH;
      const svgHeight = bbox.height || HEIGHT;

      const t = transformRef.current;
      const dx = (e.clientX - dragRef.current.startX) / t.k;
      const dy = (e.clientY - dragRef.current.startY) / t.k;

      d.x = (d.x ?? 0) + dx;
      d.y = (d.y ?? 0) + dy;
      dragRef.current.startX = e.clientX;
      dragRef.current.startY = e.clientY;

      // Update just the dragged node's SVG position directly (no React re-render)
      if (gRef.current) {
        const nodeGroup = gRef.current.querySelector(`[data-node-id="${d.id}"]`);
        if (nodeGroup) {
          nodeGroup.setAttribute("transform", `translate(${d.x},${d.y})`);
        }
      }
    },
    []
  );

  const handleNodePointerUp = useCallback(() => {
    dragRef.current.node = null;
    // Force a re-render to snap the dragged node back into the React data model
    setNodes((prev) => [...prev]);
  }, []);

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-border bg-graph-bg">
      {/* Controls bar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <span className="font-mono text-[11px] text-fg-muted">
          {nodes.length} nodes · {links.length} edges · cap {MAX_NODES}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleZoomOut}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-surface-subtle font-mono text-sm text-fg transition-colors hover:border-accent hover:text-accent"
            title="Zoom out"
          >
            −
          </button>
          <span className="min-w-[3rem] text-center font-mono text-[11px] tabular-nums text-fg-muted">
            {zoomLevel}%
          </span>
          <button
            onClick={handleZoomIn}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-surface-subtle font-mono text-sm text-fg transition-colors hover:border-accent hover:text-accent"
            title="Zoom in"
          >
            +
          </button>
          <div className="mx-1 h-4 w-px bg-border" />
          <button
            onClick={handleFitToGraph}
            className="rounded-md border border-border bg-surface-subtle px-2.5 py-1 font-sans text-[11px] font-medium text-fg transition-colors hover:border-accent hover:text-accent"
            title="Fit entire graph to viewport"
          >
            Fit
          </button>
          <button
            onClick={handleReset}
            className="rounded-md border border-border bg-surface-subtle px-2.5 py-1 font-sans text-[11px] font-medium text-fg transition-colors hover:border-accent hover:text-accent"
            title="Reset zoom and pan"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Graph viewport */}
      <div
        className="relative flex-1 overflow-hidden"
        style={{ cursor: dragRef.current.node ? "grabbing" : "grab" }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-full w-full"
          style={{ touchAction: "none" }}
        >
          <g ref={gRef} transform={transformStr}>
            {/* Edges */}
            {links.map((l) => {
              const s = l.source as GNode;
              const t = l.target as GNode;
              if (typeof s !== "object" || typeof t !== "object" || s.x == null || t.x == null)
                return null;
              const flagged = s.flagged || t.flagged;
              return (
                <line
                  key={l.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={flagged ? "var(--ring-link-flagged)" : "var(--ring-link)"}
                  strokeWidth={flagged ? 1.5 : 0.8}
                  opacity={flagged ? 0.8 : 0.4}
                />
              );
            })}

            {/* Nodes */}
            {nodes.map((n) =>
              n.x == null || n.y == null ? null : (
                <g
                  key={n.id}
                  data-node-id={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  onPointerDown={(e) => handleNodePointerDown(e, n)}
                  onPointerMove={handleNodePointerMove}
                  onPointerUp={handleNodePointerUp}
                  style={{ cursor: "pointer" }}
                >
                  {n.flagged && (
                    <circle r={16} fill="var(--ring-node-glow)" />
                  )}
                  <circle
                    r={n.flagged ? 8 : 4.5}
                    fill={n.flagged ? "var(--ring-node-flagged)" : "var(--ring-node)"}
                    stroke={n.flagged ? "var(--foreground)" : "none"}
                    strokeWidth={n.flagged ? 1.5 : 0}
                    opacity={n.flagged ? 1 : 0.8}
                  />
                  {/* Show ID on hover / always for flagged */}
                  {n.flagged && (
                    <text
                      x={12}
                      y={4}
                      fontSize={10}
                      fontFamily="var(--font-mono)"
                      fill="var(--foreground)"
                      opacity={0.8}
                    >
                      {n.id}
                    </text>
                  )}
                  <title>
                    {n.id}
                    {n.flagged ? " (flagged)" : ""}
                  </title>
                </g>
              )
            )}
          </g>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-fg-muted">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: "var(--ring-node-flagged)" }}
          />{" "}
          Flagged
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: "var(--ring-node)" }}
          />{" "}
          Normal
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4 rounded"
            style={{ background: "var(--ring-link-flagged)" }}
          />{" "}
          Ring edge
        </span>
      </div>
    </div>
  );
}
