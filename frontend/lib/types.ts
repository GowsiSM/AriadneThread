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
  | { type: "snapshot"; rings: RingPayload[]; metrics: Metrics; fairness: { cohorts: CohortStat[] }; stream: StreamStats }
  | { type: "transaction"; tx: TxMessage }
  | { type: "ring_alert"; ring: RingPayload; explanation: Explanation; blast_radius: BlastRadius }
  | { type: "metrics_update"; metrics: Metrics; fairness: { cohorts: CohortStat[] }; stream: StreamStats }
  | { type: "stream_complete"; stream: StreamStats };

export interface RingAlert {
  ring: RingPayload;
  explanation: Explanation;
  blast_radius: BlastRadius;
  receivedAt: number;
}
