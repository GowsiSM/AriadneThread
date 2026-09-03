# Architecture

## System overview

```
                     ┌────────────────────────────────────────────┐
                     │              FastAPI backend                │
                     │                                              │
synthetic  ──────►   │  data_gen.py                                 │
transaction          │     │  (seeded, labeled, 3 embedded ring     │
stream               │     │   types + realistic noise)             │
                     │     ▼                                        │
                     │  graph_engine.py  (TransactionGraph)         │
                     │     │  incremental NetworkX MultiDiGraph      │
                     │     │  + shared-attribute (device/IP) graph   │
                     │     ▼                                        │
                     │  detection.py  (run every N edges)           │
                     │     │  Louvain communities → 7-signal score  │
                     │     ▼                                        │
                     │  graph_intelligence.py                       │
                     │     │  motifs, money-flow, typology, roles,  │
                     │     │  ring decomposition (deterministic)    │
                     │     ▼                                        │
                     │  fairness.py                                 │
                     │     │  segmented FP cost + blast radius       │
                     │     ▼                                        │
                     │  ai_explainer.py                             │
                     │     │  plain-English explanation (or          │
                     │     │  template fallback) — EXPLAIN ONLY      │
                     │     ▼                                        │
                     │  db.py (SQLite, in-memory fallback)          │
                     │     │  audit log + ring records               │
                     │     ▼                                        │
                     │  websocket_manager.py  ──────────────────────┼──► WebSocket ──► Next.js dashboard
                     │  REST endpoints (/api/rings, /api/metrics…)  │            (live graph, alerts,
                     └────────────────────────────────────────────┘             blast-radius, fairness)
```

## Why a graph, not a row-by-row classifier

A single-transaction classifier answers "is this transaction suspicious?"
Fraud rings are, by definition, a *relationship* pattern — no single
transaction in a smurfing ring looks unusual in isolation; it's the
structure across transactions (a closed loop, a fan-out, a burst) that gives
it away. We model transactions plus shared-attribute edges (device, IP) as a
graph and run community detection + five structural signals instead.

## Why these signals, with these weights

See `docs/heuristic_proposals.md` for the full design trail, including
heuristics we considered and explicitly rejected. In short: each signal
targets a distinct, named fraud topology (cycles → layering, isolation →
coordinated groups, PageRank anomaly → money magnets, temporal burst → mule
dispersal, neighbor propagation → risk bleeding from confirmed rings this
run, motif presence → structural fraud patterns, flow concentration →
money-magnet hubs). Weights (25/22/18/12/8/8/7) are a documented, fixed,
auditable choice — not learned — because the track's bar requires every
money-adjacent action to be explainable and bounded, and a hand-set weighted
sum is easier for a human reviewer to audit than a trained model's implicit
weighting.

## Graph intelligence layer (Stage 3)

`graph_intelligence.py` adds a deterministic, explainable intelligence layer
on top of the raw detection score. It is pure graph algorithms — no ML, no
LLM — and every output carries human-readable evidence.

- **Motif detection** — finds structural fraud patterns: cycles, fan-in,
  fan-out, chains, layering (amount amplification), funnels, shared-device,
  shared-IP. Each motif records its nodes and an evidence string.
- **Money-flow analysis** — computes inflow/outflow across the ring boundary,
  internal circulation, net flow, flow ratio, the dominant (highest-volume)
  path, and a flow-concentration score.
- **Typology classification** — deterministically scores all 12 typologies
  (circular, fan_in, fan_out, smurfing, layering, funnel, mule_chain, burst,
  shared_device, shared_ip, pass_through, multi_hop) plus `unknown`, and
  returns the winner with confidence and evidence.
- **Role assignment** — labels each member as originator, mule, intermediary,
  collector, funnel, beneficiary, or unknown, based on in/out degree balance
  and flow position.
- **Ring decomposition** — splits large rings (20+ members) into investigable
  sub-rings of 3-8 members, each with a risk-contribution estimate and a
  reason for the split.

These enrich each `RingCandidate` with `typology`, `roles`, `flow_summary`,
`motifs`, and `sub_rings` fields, feeding the investigation workflow and the
explanation layer without changing the deterministic score contract.

## Evaluation & adversarial testing (Stage 4)

`evaluation.py` and `adversarial.py` add offline rigor on top of the
deterministic detector. See [`docs/evaluation.md`](./evaluation.md) for the
full reference.

- **Threshold sweep** — sweeps 10–95, computes per-threshold precision/recall/
  F1/FPR/TPR, and returns PR-AUC and ROC-AUC plus the F1-optimal threshold.
- **Baseline comparisons** — random, degree, and rule-based baselines are
  scored against the same ground truth and compared to the graph detector.
- **Temporal split** — splits transactions 70/30 by timestamp and measures
  detection decay between periods.
- **Held-out rings** — trains on some rings, evaluates on held-out rings.
- **Faithfulness** — verifies each candidate's explanation features are
  consistent with the score that produced it.
- **Adversarial robustness** — 8 controlled evasion variations (frequency,
  timing, external edges, innocent members, ring size, cycle-breaking, amount
  variation, spread) measure how detection degrades under attack. This is a
  unique differentiator: none of the 7 reference repos test robustness.

The Stage 3 regression baseline is preserved: top score 74.4, precision
1.000, recall 0.263, F1 0.417 at threshold 55.

## Investigation & versioning (Stage 5)

`investigation.py` and `versions.py` add a structured investigation workflow
and reproducibility. See [`docs/investigation.md`](./investigation.md) for
the full reference.

- **Case lifecycle** — every ring above threshold becomes an
  `InvestigationCase` that moves through OBSERVED → SUSPICIOUS → HIGH_RISK →
  UNDER_REVIEW → CONFIRMED / DISMISSED / RESOLVED, with a validated state
  machine and terminal states.
- **Priority** — deterministic priority (LOW/MEDIUM/HIGH/CRITICAL) from
  score, member count, and typology.
- **Audit trail** — every status change, note, assignment, and evidence
  attachment is recorded with actor and timestamp, persisted to SQLite
  (`CaseRecord`, `CaseEventRecord`) and mirrored in the extended `AuditLog`.
- **Versioning** — `DetectorVersion`, `DatasetVersion`, `FeatureVersion`, and
  `RunVersion` are deterministic SHA-256 hashes of the exact configuration,
  so every detection run is reproducible and the audit trail can answer
  "which detector version flagged this ring?"
- **REST endpoints** — `/api/cases`, `/api/cases/{id}`, transition/note/
  assign, and `/api/versions`.

## Frontend enhancements (Stage 6)

The Next.js frontend now exposes the graph-intelligence, investigation, and
evaluation layers built in Stages 3–5 as first-class pages.

- **Investigation page** (`/investigation`) — a case-management workspace that
  lists every auto-created `InvestigationCase` with status/priority badges,
  filters by status, and lets an analyst transition lifecycle states, add
  notes, assign analysts, and inspect the full audit timeline. It consumes the
  Stage 5 REST endpoints via `lib/useRestData.ts` (`useCases`, `useCaseDetail`,
  `transitionCase`, `addCaseNote`, `assignCase`).
- **Ring detail enrichment** — the ring detail page now renders the Stage 3
  graph-intelligence fields: fraud typology + confidence, per-member role
  assignments, the money-flow summary (inflow/outflow, internal/external
  volume, net flow, concentration, dominant path), detected motifs, and
  sub-ring decomposition.
- **Evaluation page** (`/evaluation`) — a new `/api/evaluation` endpoint runs
  the Stage 4 evaluation pipeline (threshold sweep with PR-AUC/ROC-AUC,
  baseline comparison, temporal split, adversarial robustness) on a fixed
  deterministic dataset and the page renders the results as tables and metric
  cards.
- **Versions page** (`/versions`) — renders the Stage 5 deterministic version
  hashes (detector/dataset/feature/run), signal weights, enabled features, and
  dataset configuration from `/api/versions`.
- **Navigation** — the sidebar gains an "Operations" section linking to
  Investigations, Evaluation, and Versions; `PageRouter` routes the new paths.

### Bug fix: `collector` typology KeyError

During Stage 6 verification, `/api/evaluation` returned HTTP 500 on the
seed=1 dataset because `classify_typology` referenced `scores["collector"]`,
but `collector` is a **role** (in `ROLES`), not a **typology** (in
`TYPOLOGIES`). The `scores` dict is initialized from `TYPOLOGIES`, so the
reference raised `KeyError`. The fix replaces the erroneous `collector`
boost with a `funnel` boost (a valid typology) alongside the existing
`fan_in` boost for high flow concentration. All 143 backend tests pass and
`/api/evaluation` returns 200.

## Stage 7: Docker verification

The full stack is containerized and verified end-to-end in Docker.

### Services

- **backend** — FastAPI (`uvicorn app.main:app`) on `:8000`, with a
  `sentinel-data` volume mounted at `/app/data` for the SQLite database.
- **frontend** — Next.js on `:3000`, with `NEXT_PUBLIC_WS_URL` and
  `NEXT_PUBLIC_API_URL` pointing at the backend.

### SPA routing fix (catch-all route)

The app is a single-page shell: `app/page.tsx` renders an `AppShell` +
`PageRouter` that switches on `usePathname()`. Next.js App Router 404s on any
sub-route (`/rings`, `/versions`, `/evaluation`, …) because no page files
exist for them. This was a pre-existing limitation affecting **all** routes.
Fixed by adding `app/[...slug]/page.tsx`, a catch-all route that renders the
same `AppShell` + `PageRouter`. All routes now resolve.

### Stale-volume migration resolution

A stale `sentinel-data` Docker volume (created by an older backend image
before Stage 5 added the `audit_log.actor` column) caused
`audit_log has no column named actor` at startup. `Base.metadata.create_all()`
creates new tables but does **not** alter existing ones, so the schema drift
persisted across rebuilds. Resolved with `docker compose down -v` (deleting
the volume) followed by a clean `--no-cache` rebuild.

### Verified in Docker

- **API** — `/api/health`, `/api/rings` (15 rings), `/api/rings/{id}` (full
  detail with typology/roles/flow/motifs), `/api/users/{id}`, `/api/cases`,
  `/api/versions`, `/api/evaluation` all return 200. `/api/transactions`
  returns 404 by design (the Transactions page consumes the WebSocket stream).
- **Regression baseline preserved** — precision 100%, recall 26.3%, F1 41.7%,
  threshold 55, TP=5, FP=0, FN=14.
- **Evaluation** — PR-AUC 0.333, ROC-AUC 0.707, best threshold 45.0,
  adversarial pass rate 1%; graph_detector beats random/rule_based/degree
  baselines.
- **Frontend** — Dashboard, Rings, RingDetail (all graph-intelligence
  sections), Metrics, Fairness, Graph, Transactions, Evaluation, Versions,
  and Investigation (5 open cases INV-0001..0005) all render correctly.

## Why AI only explains, never decides

`ai_explainer.py` is called *after* `detection.py` has already produced a
final score and the fairness module has already computed blast radius. The
LLM call receives the already-computed structured result and is instructed
to describe it, not to re-evaluate it — there is no code path where the
LLM's output feeds back into the score, the flag decision, or any
auto-action. This is deliberate: it is the same "controlled autonomy"
pattern the track's bar asks for, and it also means the system degrades
gracefully — if the AI call fails, timeouts, or has no key configured, the
system falls back to a deterministic templated explanation built from the
same signal data, and the audit trail is unaffected either way.

## Streaming, not batch

Fraud rings *form* over time; a static batch report can only ever show you
the end state. The backend replays the synthetic dataset over time
(configurable via `STREAM_TPS`), updates the graph incrementally, and
re-runs detection every `DETECTION_EVERY_N_EDGES` edges, broadcasting new
alerts over WebSocket the moment a ring crosses the score threshold. The
frontend renders this as a live, force-directed graph so a reviewer watches
a ring visibly condense rather than reading a table after the fact.

## Data model

- **Transaction**: `tx_id, ts, sender, receiver, amount, sender_device, sender_ip, is_fraud_ring_member (ground truth only), ring_id (ground truth only)`
- **User**: `user_id, device_id, ip_address, upi_handle, account_age_days, cohort, city`
- **RingCandidate** (in-memory, computed): `ring_id, members, score, signals[], key_edges[], typology, roles[], flow_summary, motifs[], sub_rings[]`
- **RingRecord** (SQLite): persisted version of a flagged `RingCandidate` plus its explanation and blast-radius snapshot at detection time
- **AuditLog** (SQLite): append-only event log — `startup`, `detection_run`, `ring_flagged`, `detection_error`, `stream_complete` — this is the audit trail the track's bar asks for

## Known limitations / honest tradeoffs

- **Recall on fan-out/burst rings is lower than on circular rings.** On the
  default synthetic dataset (seed 42), overall recall is ~0.26 at the
  default threshold — the cycle-detection signal is very strong on circular
  rings but fan-out/burst rings rely more on isolation + burst signals,
  which are noisier on a small synthetic graph. We report this honestly
  rather than tuning the threshold down to inflate the number (see
  `README.md` → "What broke, and how we got out").
- **In-process, single-worker state.** `main.py` keeps `latest_candidates`,
  the graph, and stream state as module-level globals. Fine for a
  single-instance demo; would need a shared store (Redis/Postgres) and a
  proper task queue for horizontal scaling.
- **Community detection re-runs on the full graph each cycle**, not
  incrementally. At demo scale (~1,200 transactions) this is fast (well
  under a second); at production scale this would need incremental/windowed
  Louvain or a streaming graph database.
- **Cohort cost estimates are illustrative proxies** (`fp_count * (avg_value
  * 3 + 150)`), not calibrated against real revenue/support-cost data —
  clearly labeled as such in the UI and README.
