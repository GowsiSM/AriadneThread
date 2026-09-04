export interface TxSignal {
  name: string;
  weight: number;
  value: number;
  detail: string;
}

export interface RingPayload {
  ring_id: string;
  members: string[];
  score: number;
  signals: TxSignal[];
  key_edges: [string, string][];
  // Stage 3: graph intelligence fields
  typology?: string;
  typology_confidence?: number;
  roles?: RoleAssignment[];
  flow_summary?: FlowSummary;
  motifs?: MotifMatch[];
  sub_rings?: SubRing[];
}

export interface RoleAssignment {
  user_id: string;
  role: string;
  confidence: number;
  evidence: string;
}

export interface FlowSummary {
  total_inflow: number;
  total_outflow: number;
  internal_volume: number;
  external_volume: number;
  net_flow: number;
  flow_ratio: number;
  dominant_path: string[];
  dominant_amount: number;
  concentration: number;
}

export interface MotifMatch {
  motif_type: string;
  nodes: string[];
  evidence: string;
  confidence: number;
}

export interface SubRing {
  sub_ring_id: string;
  members: string[];
  reason: string;
  risk_contribution: number;
}

export interface Explanation {
  text: string;
  source: "ai" | "template";
  error: string | null;
}

export interface BlastRadius {
  ring_id: string;
  total_members: number;
  likely_innocent: number;
  innocent_ratio: number;
  txn_volume_last_window: number;
  value_at_risk_inr: number;
  dominant_cohorts: string[];
  recommendation: string;
}

export interface Metrics {
  true_positive_users: number;
  false_positive_users: number;
  false_negative_users: number;
  precision: number;
  recall: number;
  f1: number;
  threshold: number;
}

export interface CohortStat {
  cohort: string;
  total_users: number;
  flagged_users: number;
  false_positives: number;
  fp_rate: number;
  estimated_cost_inr: number;
}

export interface TxMessage {
  tx_id: string;
  ts: string;
  sender: string;
  receiver: string;
  amount: number;
  merchant_id: string | null;
  sender_device: string;
  sender_ip: string;
  is_fraud_ring_member: boolean;
  ring_id: string | null;
}

export interface StreamStats {
  emitted: number;
  total: number;
  started: boolean;
  done: boolean;
}

export type ServerMessage =
  | { type: "snapshot"; rings: RingPayload[]; metrics: Metrics; fairness: { cohorts: CohortStat[] }; stream: StreamStats; recent_tx?: TxMessage[] }
  | { type: "transaction"; tx: TxMessage }
  | { type: "ring_alert"; ring: RingPayload; explanation: Explanation; blast_radius: BlastRadius }
  | { type: "explanation_update"; ring_id: string; explanation: Explanation }
  | { type: "metrics_update"; metrics: Metrics; fairness: { cohorts: CohortStat[] }; stream: StreamStats }
  | { type: "stream_complete"; stream: StreamStats };

export interface RingAlert {
  ring: RingPayload;
  explanation: Explanation;
  blast_radius: BlastRadius;
  receivedAt: number;
}

// ---------------------------------------------------------------------------
// Stage 5: Investigation cases
// ---------------------------------------------------------------------------

export type CaseStatus =
  | "OBSERVED"
  | "SUSPICIOUS"
  | "HIGH_RISK"
  | "UNDER_REVIEW"
  | "CONFIRMED"
  | "DISMISSED"
  | "RESOLVED";

export type CasePriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface CaseEvent {
  event_id: string;
  case_id: string;
  timestamp: string;
  event_type: string;
  from_status: CaseStatus | null;
  to_status: CaseStatus | null;
  actor: string;
  detail: Record<string, unknown>;
}

export interface InvestigationCase {
  case_id: string;
  ring_id: string;
  status: CaseStatus;
  priority: CasePriority;
  created_at: string;
  updated_at: string;
  members: string[];
  score: number;
  typology: string | null;
  assigned_to: string | null;
  notes: string[];
  evidence: Record<string, unknown>[];
  n_events: number;
  detector_version: string;
  dataset_version: string;
  timeline?: CaseEvent[];
}

export interface CaseSummary {
  total_cases: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  open_cases: number;
  closed_cases: number;
}

// ---------------------------------------------------------------------------
// Chargeback Evidence Responder
// ---------------------------------------------------------------------------

export type ChargebackStatus = "OPEN" | "UNDER_REVIEW" | "RESPONDED" | "CLOSED";
export type ChargebackPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface ChargebackCase {
  case_id: string;
  transaction_id: string;
  cardholder_id: string;
  merchant_id: string;
  amount: number;
  currency: string;
  reason_code: string;
  reason_description: string;
  filed_at: string;
  status: ChargebackStatus;
  priority: ChargebackPriority;
  is_fraud: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvidenceItem {
  category: string;
  type: string;
  description: string;
  value: unknown;
  strength: number;
  collected_at: string;
}

export interface ChargebackResponse {
  case_id: string;
  recommendation: "CONTEST" | "ACCEPT" | "REQUEST_MORE_INFO";
  confidence: number;
  evidence_summary: string;
  response_text: string;
  evidence_count: number;
  strong_evidence_count: number;
  generated_at: string;
}

export interface ChargebackPrediction {
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  available: boolean;
  explanation: string;
}

// ---------------------------------------------------------------------------
// Stage 5: Versions
// ---------------------------------------------------------------------------

export interface VersionInfo {
  detector_version: string;
  dataset_version: string;
  feature_version: string;
  run_version: string;
  signal_weights: Record<string, number>;
  threshold: number;
  features: string[];
  dataset_config: Record<string, number>;
}
