# Frontend

Next.js 14 (App Router) single-page application that renders the AriadneThread
backend's live stream and REST APIs. Pages are `"use client"` components
switched by `PageRouter` based on the current pathname.

## Data sources

- **WebSocket** (`ws://localhost:8000/ws/stream`) — live transaction stream,
  ring alerts, metrics, and fairness updates via `SentinelDataProvider`
  (React context). Used by Dashboard, Rings, Transactions, Graph, Fairness,
  and Metrics pages.
- **REST** (`http://localhost:8000`) — investigation cases, chargeback cases,
  versions, and evaluation via `lib/useRestData.ts` hooks that poll on an
  interval.

## Pages

| Route | Component | Data |
|---|---|---|
| `/` | DashboardPage | WS snapshot |
| `/rings` | RingsPage | WS alerts |
| `/rings/[id]` | RingDetailPage | WS alert + graph intelligence fields |
| `/transactions` | TransactionsPage | WS recent tx |
| `/graph` | GraphPage | WS recent tx + alerts |
| `/fairness` | FairnessPage | WS cohorts |
| `/metrics` | MetricsPage | WS metrics |
| `/investigation` | InvestigationPage | REST `/api/cases` |
| `/chargebacks` | ChargebackPage | REST `/api/chargeback/cases` |
| `/chargebacks/[id]` | ChargebackCasePage | REST `/api/chargeback/evidence/{id}` + `/response/{id}` |
| `/evaluation` | EvaluationPage | REST `/api/evaluation` |
| `/versions` | VersionsPage | REST `/api/versions` |

## Investigation page

`components/pages/InvestigationPage.tsx` is a case-management workspace:

- Lists all `InvestigationCase` records with status and priority badges
- Filters by lifecycle status (OBSERVED → … → RESOLVED)
- Selecting a case loads its detail and shows ring link, score, typology,
  members, lifecycle transition buttons, note input, analyst assignment, and
  the full audit timeline

The allowed transitions are mirrored in `components/caseBadges.ts`
(`nextTransitions`) so the UI only offers valid moves.

## Chargeback pages

`components/pages/ChargebackPage.tsx` lists chargeback cases with status
filtering. `components/pages/ChargebackCasePage.tsx` shows case detail with:

- **Prioritized evidence** — ordered by relevance to the chargeback reason
- **Recommendation** — accept / contest / request more info
- **Narrative** — human-readable summary of the evidence
- **Evidence strength** — overall confidence score

## Ring detail enrichment

`components/pages/RingDetailPage.tsx` renders the graph-intelligence fields
included in each ring payload:

- **Typology** — fraud pattern label + confidence
- **Roles** — per-member role assignment with confidence
- **Flow summary** — inflow/outflow, internal/external volume, net flow,
  flow ratio, concentration, dominant money path
- **Motifs** — detected structural motifs with nodes, evidence, confidence
- **Sub-rings** — decomposed sub-rings with members, reason, risk contribution

## Evaluation page

`components/pages/EvaluationPage.tsx` calls `/api/evaluation`, which runs the
evaluation pipeline on a fixed deterministic dataset and returns:

- **Threshold sweep** — per-threshold precision/recall/F1, PR-AUC, ROC-AUC
- **Baseline comparison** — random, degree, rule-based, graph detector
- **Temporal split** — train/test F1 and decay rate
- **Adversarial robustness** — per-variation score drop and pass rate

## Versions page

`components/pages/VersionsPage.tsx` renders the deterministic version hashes
(`det-…`, `ds-…`, `feat-…`, `run-…`), signal weights, enabled features, and
dataset configuration from `/api/versions`.

## Shared UI

Reusable primitives live in `components/`: `SectionCard`, `MetricCard`,
`RiskBadge`, `StatusBadge`, `PageHeader`, `EmptyState`/`LoadingState`.
Styling uses Tailwind with custom theme tokens (`bg-surface`, `text-fg`,
`text-fg-muted`, `border-border`, `bg-accent`, `text-danger/warning/success/
info`).
