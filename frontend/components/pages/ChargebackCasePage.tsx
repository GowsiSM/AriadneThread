"use client";

import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { LoadingState } from "@/components/States";
import {
  useChargebackCase,
  useChargebackEvidence,
  useChargebackResponse,
} from "@/lib/useRestData";
import type { EvidenceItem } from "@/lib/types";

const STATUS_VARIANTS: Record<string, "info" | "success" | "warning" | "danger" | "neutral"> = {
  OPEN: "warning",
  UNDER_REVIEW: "info",
  RESPONDED: "success",
  CLOSED: "neutral",
};

const RECOMMENDATION_VARIANTS: Record<string, "success" | "danger" | "warning"> = {
  CONTEST: "success",
  ACCEPT: "danger",
  REQUEST_MORE_INFO: "warning",
};

function formatDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatCurrency(amount: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency === "INR" ? "INR" : "USD",
  }).format(amount);
}

function StrengthBar({ strength }: { strength: number }) {
  const pct = Math.round(strength * 100);
  const color =
    strength >= 0.7 ? "bg-success" : strength >= 0.4 ? "bg-warning" : "bg-danger";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-surface-subtle">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[10px] text-fg-muted">{pct}%</span>
    </div>
  );
}

function EvidenceCard({ item }: { item: EvidenceItem }) {
  const valueStr =
    item.value != null
      ? typeof item.value === "string"
        ? item.value
        : JSON.stringify(item.value, null, 2)
      : null;

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded bg-surface-subtle px-1.5 py-0.5 font-mono text-[10px] text-fg-muted">
            {item.category}
          </span>
          <span className="text-xs font-medium text-fg">{item.type}</span>
        </div>
        <StrengthBar strength={item.strength} />
      </div>
      <p className="mt-1.5 text-xs text-fg-secondary">{item.description}</p>
      {valueStr && (
        <pre className="mt-2 max-h-24 overflow-auto rounded bg-surface-subtle p-2 font-mono text-[10px] text-fg-muted">
          {valueStr}
        </pre>
      )}
    </div>
  );
}

export default function ChargebackCasePage({ caseId }: { caseId: string }) {
  const { caseData, loading: caseLoading } = useChargebackCase(caseId);
  const { evidence, loading: evidenceLoading } = useChargebackEvidence(caseId);
  const { response, loading: responseLoading } = useChargebackResponse(caseId);

  if (caseLoading || evidenceLoading || responseLoading) return <LoadingState />;
  if (!caseData) {
    return (
      <div className="space-y-4">
        <PageHeader title="Case Not Found" description={`No case found for ${caseId}`} />
        <Link href="/chargebacks" className="text-sm text-accent hover:underline">
          ← Back to chargebacks
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/chargebacks" className="mb-2 inline-block text-xs text-accent hover:underline">
          ← Back to chargebacks
        </Link>
        <PageHeader
          title={`Chargeback ${caseData.case_id.slice(0, 12)}…`}
          description={caseData.reason_description}
        />
      </div>

      {/* Case details */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <InfoCard label="Status">
          <StatusBadge variant={STATUS_VARIANTS[caseData.status] ?? "neutral"}>
            {caseData.status}
          </StatusBadge>
        </InfoCard>
        <InfoCard label="Amount">
          {formatCurrency(caseData.amount, caseData.currency)}
        </InfoCard>
        <InfoCard label="Reason Code">{caseData.reason_code}</InfoCard>
        <InfoCard label="Cardholder">{caseData.cardholder_id}</InfoCard>
        <InfoCard label="Merchant">{caseData.merchant_id}</InfoCard>
        <InfoCard label="Filed">{formatDate(caseData.filed_at)}</InfoCard>
        <InfoCard label="Transaction">{caseData.transaction_id}</InfoCard>
        <InfoCard label="Fraud Flag">
          {caseData.is_fraud ? (
            <span className="text-danger font-medium">Yes</span>
          ) : (
            <span className="text-fg-muted">No</span>
          )}
        </InfoCard>
        <InfoCard label="Priority">
          <StatusBadge variant={caseData.priority === "CRITICAL" ? "danger" : caseData.priority === "HIGH" ? "warning" : "info"}>
            {caseData.priority}
          </StatusBadge>
        </InfoCard>
      </div>

      {/* ML Response recommendation */}
      {response && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-medium text-fg">ML Response Recommendation</h3>
          <div className="flex items-center gap-3">
            <StatusBadge variant={RECOMMENDATION_VARIANTS[response.recommendation] ?? "neutral"}>
              {response.recommendation}
            </StatusBadge>
            <span className="text-xs text-fg-muted">
              Confidence: {Math.round(response.confidence * 100)}%
            </span>
            <span className="text-xs text-fg-muted">
              {response.strong_evidence_count}/{response.evidence_count} strong evidence
            </span>
          </div>
          <p className="mt-2 text-xs text-fg-secondary">{response.response_text}</p>
        </div>
      )}

      {/* Evidence list */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-fg">
          Evidence ({evidence.length} items)
        </h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {evidence.map((item, i) => (
            <EvidenceCard key={`${item.category}-${item.type}-${i}`} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}

function InfoCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-fg-muted">{label}</div>
      <div className="mt-0.5 text-sm text-fg">{children}</div>
    </div>
  );
}
