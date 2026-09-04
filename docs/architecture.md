# Architecture

## System overview

```
                     ┌────────────────────────────────────────────┐
                     │              FastAPI backend                │
                     │                                              │
synthetic  ──────►   │  synthetic.py                                │
transaction          │     │  (seeded, labeled, 12 typologies)      │
stream               │     ▼                                        │
                     │  graph_engine.py  (TransactionGraph)         │
                     │     │  incremental NetworkX MultiDiGraph      │
                     │     ▼                                        │
                     │  detection.py  (run every N edges)           │
                     │     │  Louvain communities → 7-signal score  │
                     │     ▼                                        │
                     │  graph_intelligence.py                       │
                     │     │  motifs, money-flow, typology, roles   │
                     │     ▼                                        │
                     │  fairness.py                                 │
                     │     │  segmented FP cost + blast radius       │
                     │     ▼                                        │
                     │  ai_explainer.py                             │
                     │     │  plain-English explanation (EXPLAIN     │
                     │     │  ONLY, never decides)                  │
                     │     ▼                                        │
                     │  ml/predictor.py                             │
                     │     │  XGBoost chargeback risk scoring       │
                     │     ▼                                        │
                     │  chargeback/                                 │
                     │     │  evidence + priority + response        │
                     │     ▼                                        │
                     │  db.py (SQLite, in-memory fallback)          │
                     │     ▼                                        │
                     │  websocket_manager.py ───────────────────────┼──► WebSocket ──► Next.js dashboard
                     │  REST endpoints (/api/rings, /api/metrics…)  │
                     └────────────────────────────────────────────┘
```

## Why a graph, not a row-by-row classifier

A single-transaction classifier answers "is this transaction suspicious?"
Fraud rings are a *relationship* pattern — no single transaction in a
smurfing ring looks unusual in isolation; it's the structure across
transactions (a closed loop, a fan-out, a burst) that gives it away. We
model transactions plus shared-attribute edges (device, IP) as a graph and
run community detection + seven structural signals instead.

## Detection signals

Each signal targets a distinct fraud topology. Weights are fixed and
documented (not learned) so every money-adjacent action is auditable.

| Signal | Targets |
|---|---|
| Cycle involvement | Layering / circular money loops |
| Community isolation | Coordinated groups |
| PageRank anomaly | Money magnets |
| Temporal burst | Mule dispersal |
| Neighbor propagation | Risk from confirmed rings |
| Motif presence | Structural fraud patterns |
| Flow concentration | Money-magnet hubs |

## Graph intelligence layer

`graph_intelligence.py` adds a deterministic, explainable layer on top of
the raw detection score. Pure graph algorithms — no ML, no LLM.

- **Motif detection** — cycles, fan-in, fan-out, chains, layering, funnels,
  shared-device, shared-IP
- **Money-flow analysis** — inflow/outflow, internal circulation, net flow,
  flow ratio, dominant path, concentration
- **Typology classification** — scores all 12 typologies, returns winner with
  confidence and evidence
- **Role assignment** — originator, mule, intermediary, collector, funnel,
  beneficiary
- **Ring decomposition** — splits large rings into investigable sub-rings

## Evaluation & adversarial testing

`evaluation.py` and `adversarial.py` add offline rigor. See
[`docs/evaluation.md`](./evaluation.md) for the full reference.

- **Threshold sweep** — precision/recall/F1/FPR/TPR per threshold, PR-AUC,
  ROC-AUC
- **Baseline comparisons** — random, degree, rule-based vs. graph detector
- **Temporal split** — 70/30 train/test, detection decay
- **Held-out rings** — train on some rings, evaluate on others
- **Faithfulness** — explanation features consistent with score
- **Adversarial robustness** — 8 evasion variations measure degradation

## Investigation & versioning

`investigation.py` and `versions.py` add a structured case workflow and
reproducibility. See [`docs/investigation.md`](./investigation.md).

- **Case lifecycle** — OBSERVED → SUSPICIOUS → HIGH_RISK → UNDER_REVIEW →
  CONFIRMED / DISMISSED / RESOLVED
- **Priority** — deterministic from score, member count, typology
- **Audit trail** — every status change, note, assignment recorded with actor
  and timestamp
- **Versioning** — SHA-256 hashes of detector/dataset/feature/run config

## ML chargeback predictor

`ml/predictor.py` loads a trained XGBoost model and produces a per-transaction
fraud risk score + level + explanation. It is a *supplementary* layer on top
of the deterministic graph detector — it never replaces graph detection.

- **14 engineered features** matching the training pipeline
- **Risk levels** — HIGH (> 0.7), MEDIUM (> 0.3), LOW
- **Graceful fallback** — deterministic heuristics if the model is unavailable

## Chargeback evidence responder

`chargeback/` collects and packages evidence for card disputes.

- **EvidenceEngine** — transaction, customer, device, authentication,
  delivery, and ML risk evidence
- **EvidencePriority** — ranks evidence by chargeback reason code
- **ResponseGenerator** — builds a response package with recommendation
  (accept / contest / request more info) and narrative

## Why AI only explains, never decides

`ai_explainer.py` is called *after* detection has produced a final score and
fairness has computed blast radius. The LLM receives the already-computed
structured result and describes it — there is no code path where the LLM's
output feeds back into the score, flag decision, or any auto-action. If the
AI call fails or has no key configured, the system falls back to a
deterministic templated explanation.

## Streaming, not batch

The backend replays the synthetic dataset over time (configurable via
`STREAM_TPS`), updates the graph incrementally, and re-runs detection every
`DETECTION_EVERY_N_EDGES` edges, broadcasting alerts over WebSocket the
moment a ring crosses the threshold. The frontend renders this as a live,
force-directed graph.

## Data model

- **Transaction**: `tx_id, ts, sender, receiver, amount, sender_device, sender_ip, is_fraud_ring_member (ground truth only), ring_id (ground truth only)`
- **User**: `user_id, device_id, ip_address, upi_handle, account_age_days, cohort, city`
- **RingCandidate** (in-memory): `ring_id, members, score, signals[], key_edges[], typology, roles[], flow_summary, motifs[], sub_rings[]`
- **RingRecord** (SQLite): persisted flagged `RingCandidate` + explanation + blast radius
- **AuditLog** (SQLite): append-only event log — `startup`, `detection_run`, `ring_flagged`, `detection_error`, `stream_complete`

## Known limitations

- **Recall on fan-out/burst rings is lower than on circular rings.** Cycle
  detection is strong on circular rings; fan-out/burst relies on noisier
  isolation + burst signals.
- **In-process, single-worker state.** Module-level globals for graph, stream,
  and candidates. Fine for a single-instance demo; would need Redis/Postgres
  for horizontal scaling.
- **Community detection re-runs on the full graph each cycle.** Fast at demo
  scale (~1,200 transactions); would need incremental/windowed Louvain at
  production scale.
- **Cohort cost estimates are illustrative proxies**, not calibrated against
  real revenue/support-cost data.
