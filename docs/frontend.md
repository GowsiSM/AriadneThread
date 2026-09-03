# Frontend

The frontend is a Next.js 14 (App Router) single-page application that renders
the Fraud Ring Sentinel backend's live stream and REST APIs. It is a
client-side dashboard: pages are `"use client"` components switched by
`PageRouter` based on the current pathname.

## Data sources

- **WebSocket** (`ws://localhost:8000/ws/stream`) — live transaction stream,
  ring alerts, metrics, and fairness updates, delivered through
  `SentinelDataProvider` (React context). Used by the Dashboard, Rings,
  Transactions, Graph, Fairness, and Metrics pages.
- **REST** (`http://localhost:8000`) — investigation cases, versions, and
  evaluation, consumed through `lib/useRestData.ts` hooks that poll on an
  interval. Used by the Investigation, Evaluation, and Versions pages.

## Pages

| Route | Component | Data |
| --- | --- | --- |
| `/` | DashboardPage | WS snapshot |
| `/rings` | RingsPage | WS alerts |
| `/rings/[id]` | RingDetailPage | WS alert + graph intelligence fields |
| `/transactions` | TransactionsPage | WS recent tx |
| `/graph` | GraphPage | WS recent tx + alerts |
| `/fairness` | FairnessPage | WS cohorts |
| `/metrics` | MetricsPage | WS metrics |
| `/investigation` | InvestigationPage | REST `/api/cases` |
| `/evaluation` | EvaluationPage | REST `/api/evaluation` |
| `/versions` | VersionsPage | REST `/api/versions` |

## Investigation page

`components/pages/InvestigationPage.tsx` is a case-management workspace:

- Lists all `InvestigationCase` records with status and priority badges.
- Filters by lifecycle status (OBSERVED → … → RESOLVED).
- Selecting a case loads its detail (via `useCaseDetail`) and shows:
  - ring link, score, typology, members;
  - lifecycle transition buttons (only valid next states, matching the
    backend state machine in `caseBadges.ts`);
  - note input and analyst assignment;
  - the full audit timeline with status-change badges and event detail.

The allowed transitions are mirrored in `components/caseBadges.ts`
(`nextTransitions`) so the UI only offers valid moves.

## Ring detail enrichment

`components/pages/RingDetailPage.tsx` renders the Stage 3 graph-intelligence
fields that the backend now includes in each ring payload:

- **Typology** — fraud pattern label + confidence.
- **Roles** — per-member role assignment with confidence.
- **Flow summary** — total inflow/outflow, internal/external volume, net flow,
  flow ratio, concentration, and the dominant money path.
- **Motifs** — detected structural motifs with nodes, evidence, confidence.
- **Sub-rings** — decomposed sub-rings with members, reason, and risk
  contribution.

## Evaluation page

`components/pages/EvaluationPage.tsx` calls the new `/api/evaluation` endpoint,
which runs the Stage 4 pipeline on a fixed deterministic dataset
(`n_background_users=150, n_background_tx=500, n_rings=3, seed=1`) and returns:

- **Threshold sweep** — per-threshold precision/recall/F1 plus PR-AUC and
  ROC-AUC, with the current operating threshold highlighted.
- **Baseline comparison** — random, degree, rule-based, and the graph
  detector, sorted by F1.
- **Temporal split** — train/test F1 and decay rate.
- **Adversarial robustness** — per-variation score drop and whether detection
  was maintained, plus aggregate pass rate.

## Versions page

`components/pages/VersionsPage.tsx` renders the Stage 5 deterministic version
hashes (`det-…`, `ds-…`, `feat-…`, `run-…`), the signal weights, enabled
features, and dataset configuration from `/api/versions`.

## Shared UI

Reusable primitives live in `components/`: `SectionCard`, `MetricCard`,
`RiskBadge`, `StatusBadge`, `PageHeader`, `EmptyState`/`LoadingState`. Styling
uses Tailwind with custom theme tokens (`bg-surface`, `text-fg`,
`text-fg-muted`, `border-border`, `bg-accent`, `text-danger/warning/success/
info`).
