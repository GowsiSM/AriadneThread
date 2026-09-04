"use client";

import { useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { EmptyState, LoadingState } from "@/components/States";
import { useChargebackCases } from "@/lib/useRestData";
import type { ChargebackCase, ChargebackStatus } from "@/lib/types";

const STATUS_VARIANTS: Record<string, "info" | "success" | "warning" | "danger" | "neutral"> = {
  OPEN: "warning",
  UNDER_REVIEW: "info",
  RESPONDED: "success",
  CLOSED: "neutral",
};

const PRIORITY_VARIANTS: Record<string, "info" | "success" | "warning" | "danger" | "neutral"> = {
  LOW: "neutral",
  MEDIUM: "info",
  HIGH: "warning",
  CRITICAL: "danger",
};

function formatDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatCurrency(amount: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency === "INR" ? "INR" : "USD",
  }).format(amount);
}

function CaseRow({ c }: { c: ChargebackCase }) {
  return (
    <Link
      href={`/chargebacks/${c.case_id}`}
      className="flex items-center gap-4 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent/30 hover:bg-surface-subtle"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-fg-muted">{c.case_id.slice(0, 12)}…</span>
          <StatusBadge variant={STATUS_VARIANTS[c.status] ?? "neutral"}>{c.status}</StatusBadge>
          <StatusBadge variant={PRIORITY_VARIANTS[c.priority] ?? "neutral"}>{c.priority}</StatusBadge>
        </div>
        <div className="mt-1 text-sm text-fg">
          {c.reason_description}
        </div>
        <div className="mt-0.5 font-mono text-xs text-fg-muted">
          Tx: {c.transaction_id.slice(0, 16)}… · Filed {formatDate(c.filed_at)}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm font-medium text-fg">{formatCurrency(c.amount, c.currency ?? "INR")}</div>
        <div className="text-xs text-fg-muted">{c.merchant}</div>
      </div>
      {c.is_fraud && (
        <span className="rounded bg-danger/10 px-1.5 py-0.5 text-[10px] font-medium text-danger">
          FRAUD
        </span>
      )}
    </Link>
  );
}

export default function ChargebackPage() {
  const { cases, loading, error } = useChargebackCases();
  const [statusFilter, setStatusFilter] = useState<ChargebackStatus | "ALL">("ALL");

  const filtered = statusFilter === "ALL" ? cases : cases.filter((c) => c.status === statusFilter);

  const statusCounts = cases.reduce(
    (acc, c) => {
      acc[c.status] = (acc[c.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Chargeback Cases"
        description="ML-powered chargeback evidence responder for card disputes"
      />

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(["OPEN", "UNDER_REVIEW", "RESPONDED", "CLOSED"] as const).map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(statusFilter === status ? "ALL" : status)}
            className={`rounded-lg border px-3 py-2 text-left transition-colors ${
              statusFilter === status
                ? "border-accent bg-accent/5"
                : "border-border bg-surface hover:bg-surface-subtle"
            }`}
          >
            <div className="text-xs text-fg-muted">{status.replace("_", " ")}</div>
            <div className="text-lg font-semibold text-fg">{statusCounts[status] ?? 0}</div>
          </button>
        ))}
      </div>

      {statusFilter !== "ALL" && (
        <div className="flex items-center gap-2 text-xs text-fg-muted">
          Showing {filtered.length} cases with status{" "}
          <StatusBadge variant={STATUS_VARIANTS[statusFilter] ?? "neutral"}>{statusFilter}</StatusBadge>
          <button onClick={() => setStatusFilter("ALL")} className="text-accent hover:underline">
            Clear filter
          </button>
        </div>
      )}

      {/* Case list */}
      {loading ? (
        <LoadingState />
      ) : error ? (
        <div className="rounded-lg border border-danger/20 bg-danger/5 p-4 text-sm text-danger">{error}</div>
      ) : filtered.length === 0 ? (
        <EmptyState title="No chargeback cases found." description="Cases will appear here once chargebacks are filed." />
      ) : (
        <div className="space-y-2">
          {filtered.map((c) => (
            <CaseRow key={c.case_id} c={c} />
          ))}
        </div>
      )}
    </div>
  );
}
