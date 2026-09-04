"use client";

import { useEffect, useState } from "react";

export function EmptyState({
  icon = "○",
  title,
  description,
  action,
}: {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <span className="mb-3 text-2xl text-fg-muted">{icon}</span>
      <p className="text-sm font-medium text-fg-secondary">{title}</p>
      {description && (
        <p className="mt-1 max-w-sm text-xs text-fg-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

const CYCLE_MESSAGES = [
  "Establishing Secure Tunnel…",
  "Validating Telemetry…",
  "Syncing Node State…",
  "Decrypting Payload…",
  "Mapping Graph Topology…",
  "Running Risk Inference…",
  "Fingerprinting Entities…",
  "Compiling Audit Trail…",
];

export function LoadingState({
  message,
  cycleMessages = false,
}: {
  message?: string;
  cycleMessages?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const [msgIndex, setMsgIndex] = useState(0);

  // Fade-in on mount
  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  // Optional dynamic message cycling
  useEffect(() => {
    if (!cycleMessages) return;
    const interval = setInterval(() => {
      setMsgIndex((i) => (i + 1) % CYCLE_MESSAGES.length);
    }, 2000);
    return () => clearInterval(interval);
  }, [cycleMessages]);

  const displayText = message ?? CYCLE_MESSAGES[msgIndex];

  return (
    <div
      className={`
        absolute inset-0 z-50 flex flex-col items-center justify-center
        bg-black transition-opacity duration-500
        ${visible ? "opacity-100" : "opacity-0"}
      `}
    >
      {/* Dual-ring spinner */}
      <div className="relative mb-6 h-16 w-16">
        {/* Outer ring — slow clockwise, dashed slate */}
        <div className="absolute inset-0 animate-slow-spin rounded-full border-2 border-dashed border-slate-600" />

        {/* Inner ring — counter-clockwise, white accent */}
        <div className="absolute inset-2 animate-counter-spin rounded-full border-2 border-white" />

        {/* Pulsing glow core */}
        <div className="absolute inset-0 m-auto h-3 w-3 rounded-full bg-white shadow-[0_0_15px_rgba(255,255,255,0.5)]" />
      </div>

      {/* Status text */}
      <p className="font-mono text-xs tracking-wider text-slate-300 transition-opacity duration-300">
        {displayText}
      </p>
    </div>
  );
}
