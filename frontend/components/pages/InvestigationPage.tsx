"use client";

import { useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { EmptyState, LoadingState } from "@/components/States";
import {
  useCases,
  useCaseDetail,
  transitionCase,
  addCaseNote,
  assignCase,
} from "@/lib/useRestData";
import {
  caseStatusVariant,
  casePriorityVariant,
  nextTransitions,
} from "@/components/caseBadges";
import type { InvestigationCase, CaseStatus } from "@/lib/types";

const STATUS_ORDER: CaseStatus[] = [
  "OBSERVED",
  "SUSPICIOUS",
  "HIGH_RISK",
  "UNDER_REVIEW",
  "CONFIRMED",
  "DISMISSED",
  "RESOLVED",
];

function formatTime(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function CaseRow({
  c,
  onSelect,
  selected,
}: {
  c: InvestigationCase;
  onSelect: (id: string) => void;
  selected: boolean;
}) {
  return (
    <button
      onClick={() => onSelect(c.case_id)}
      className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
        selected
          ? "border-accent bg-surface-subtle"
          : "border-border bg-surface hover:bg-surface-hover"
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-fg">
            {c.case_id}
          </span>
          <StatusBadge variant={caseStatusVariant(c.status)} dot>
            {c.status}
          </StatusBadge>
          <StatusBadge variant={casePriorityVariant(c.priority)}>
            {c.priority}
          </StatusBadge>
        </div>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-fg-muted">
          <span className="font-mono">{c.ring_id}</span>
          <span>·</span>
          <span>{c.members.length} members</span>
          <span>·</span>
          <span>score {c.score.toFixed(1)}</span>
          {c.typology && (
            <>
              <span>·</span>
              <span className="text-fg-secondary">{c.typology}</span>
            </>
          )}
        </div>
      </div>
      <div className="shrink-0 text-right text-[11px] text-fg-muted">
        <div>{formatTime(c.updated_at)}</div>
        {c.assigned_to && (
          <div className="mt-0.5 text-fg-secondary">@{c.assigned_to}</div>
        )}
      </div>
    </button>
  );
}

function CaseDetail({
  caseId,
  onRefresh,
}: {
  caseId: string;
  onRefresh: () => void;
}) {
  const { caseData, loading, error } = useCaseDetail(caseId);
  const [note, setNote] = useState("");
  const [analyst, setAnalyst] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (loading && !caseData)
    return <LoadingState message="Establishing Secure Tunnel…" />;
  if (error && !caseData)
    return (
      <EmptyState icon="⚠" title="Failed to load case" description={error} />
    );
  if (!caseData)
    return (
      <EmptyState
        icon="○"
        title="Select a case"
        description="Choose a case from the list to inspect it."
      />
    );

  const c = caseData;
  const transitions = nextTransitions(c.status);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-fg">
            {c.case_id}
          </span>
          <StatusBadge variant={caseStatusVariant(c.status)} dot>
            {c.status}
          </StatusBadge>
          <StatusBadge variant={casePriorityVariant(c.priority)}>
            {c.priority}
          </StatusBadge>
          {c.assigned_to && (
            <StatusBadge variant="info">assigned: {c.assigned_to}</StatusBadge>
          )}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg bg-surface-subtle p-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Ring
            </div>
            <Link
              href={`/rings/${c.ring_id}`}
              className="mt-0.5 block font-mono text-xs text-accent hover:underline"
            >
              {c.ring_id}
            </Link>
          </div>
          <div className="rounded-lg bg-surface-subtle p-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Score
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
              {c.score.toFixed(1)}
            </div>
          </div>
          <div className="rounded-lg bg-surface-subtle p-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Typology
            </div>
            <div className="mt-0.5 text-sm text-fg-secondary">
              {c.typology ?? "—"}
            </div>
          </div>
          <div className="rounded-lg bg-surface-subtle p-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Members
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
              {c.members.length}
            </div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {c.members.map((m) => (
            <span
              key={m}
              className="rounded-md border border-border bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-fg-secondary"
            >
              {m}
            </span>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="card p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Actions
        </h3>
        {transitions.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {transitions.map((t) => (
              <button
                key={t}
                disabled={busy}
                onClick={() => run(() => transitionCase(c.case_id, t))}
                className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
              >
                → {t}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-fg-muted">
            This case is in a terminal state.
          </p>
        )}

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note…"
            className="flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-fg placeholder:text-fg-muted focus:border-accent focus:outline-none"
          />
          <button
            disabled={busy || !note.trim()}
            onClick={() =>
              run(async () => {
                await addCaseNote(c.case_id, note.trim());
                setNote("");
              })
            }
            className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            Add note
          </button>
        </div>

        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            value={analyst}
            onChange={(e) => setAnalyst(e.target.value)}
            placeholder="Analyst name…"
            className="flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-fg placeholder:text-fg-muted focus:border-accent focus:outline-none"
          />
          <button
            disabled={busy || !analyst.trim()}
            onClick={() =>
              run(async () => {
                await assignCase(c.case_id, analyst.trim());
                setAnalyst("");
              })
            }
            className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
          >
            Assign
          </button>
        </div>

        {actionError && (
          <p className="mt-2 text-xs text-danger">{actionError}</p>
        )}
      </div>

      {/* Notes */}
      {c.notes.length > 0 && (
        <div className="card p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-muted">
            Notes
          </h3>
          <div className="flex flex-col gap-2">
            {c.notes.map((n, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-surface-subtle px-3 py-2 text-xs text-fg-secondary"
              >
                {n}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Timeline
        </h3>
        {c.timeline && c.timeline.length > 0 ? (
          <div className="flex flex-col gap-3">
            {c.timeline.map((ev) => (
              <div key={ev.event_id} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="mt-1 h-2 w-2 rounded-full bg-accent" />
                  <span className="w-px flex-1 bg-border" />
                </div>
                <div className="pb-1">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-medium text-fg">
                      {ev.event_type.replace(/_/g, " ")}
                    </span>
                    <span className="text-fg-muted">
                      · {formatTime(ev.timestamp)}
                    </span>
                    <span className="text-fg-muted">· {ev.actor}</span>
                  </div>
                  {(ev.from_status || ev.to_status) && (
                    <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-fg-secondary">
                      {ev.from_status && (
                        <StatusBadge variant="neutral">
                          {ev.from_status}
                        </StatusBadge>
                      )}
                      {ev.from_status && ev.to_status && (
                        <span className="text-fg-muted">→</span>
                      )}
                      {ev.to_status && (
                        <StatusBadge variant={caseStatusVariant(ev.to_status)}>
                          {ev.to_status}
                        </StatusBadge>
                      )}
                    </div>
                  )}
                  {ev.detail && Object.keys(ev.detail).length > 0 && (
                    <pre className="mt-1 overflow-x-auto rounded-md bg-surface-subtle p-2 text-[10px] text-fg-muted">
                      {JSON.stringify(ev.detail, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-fg-muted">No timeline events yet.</p>
        )}
      </div>
    </div>
  );
}

export default function InvestigationPage() {
  const { cases, summary, loading, error, refresh } = useCases();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CaseStatus | "ALL">("ALL");

  const filtered =
    statusFilter === "ALL"
      ? cases
      : cases.filter((c) => c.status === statusFilter);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Investigations"
        description="Case lifecycle management for detected fraud rings"
      >
        {summary && (
          <div className="flex items-center gap-2">
            <StatusBadge variant="warning">
              {summary.open_cases} open
            </StatusBadge>
            <StatusBadge variant="success">
              {summary.closed_cases} closed
            </StatusBadge>
          </div>
        )}
      </PageHeader>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Total cases
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
              {summary.total_cases}
            </div>
          </div>
          <div className="card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Open
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-warning">
              {summary.open_cases}
            </div>
          </div>
          <div className="card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Closed
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-success">
              {summary.closed_cases}
            </div>
          </div>
          <div className="card px-4 py-3">
            <div className="text-[10px] uppercase tracking-wider text-fg-muted">
              Critical
            </div>
            <div className="mt-0.5 font-mono text-lg font-semibold text-danger">
              {summary.by_priority?.CRITICAL ?? 0}
            </div>
          </div>
        </div>
      )}

      {/* Status filter */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setStatusFilter("ALL")}
          className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
            statusFilter === "ALL"
              ? "border-accent bg-accent/10 text-accent"
              : "border-border text-fg-muted hover:text-fg"
          }`}
        >
          All
        </button>
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
              statusFilter === s
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && cases.length === 0 ? (
        <LoadingState cycleMessages />
      ) : error && cases.length === 0 ? (
        <EmptyState icon="⚠" title="Failed to load cases" description={error} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="◫"
          title="No cases"
          description="No investigation cases match this filter yet. Cases are auto-created when rings are detected."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Case list */}
          <div className="flex flex-col gap-2">
            {filtered.map((c) => (
              <CaseRow
                key={c.case_id}
                c={c}
                selected={c.case_id === selectedId}
                onSelect={setSelectedId}
              />
            ))}
          </div>
          {/* Detail */}
          <div>
            {selectedId ? (
              <CaseDetail caseId={selectedId} onRefresh={refresh} />
            ) : (
              <EmptyState
                icon="◫"
                title="Select a case"
                description="Click a case on the left to inspect its lifecycle, notes, and timeline."
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
