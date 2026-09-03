# Investigation & Versioning (Stage 5)

This document describes the investigation case workflow and detector/dataset/
feature versioning added in Stage 5. It complements
[`architecture.md`](./architecture.md) and [`evaluation.md`](./evaluation.md).

## Goals

1. **Turn a score into an investigation hypothesis** — every ring that
   crosses the detection threshold becomes a structured case an analyst can
   triage, escalate, and resolve.
2. **Enforce a lifecycle** — OBSERVED → SUSPICIOUS → HIGH_RISK → UNDER_REVIEW
   → CONFIRMED / DISMISSED / RESOLVED, with validated transitions.
3. **Keep a full audit trail** — every status change, note, assignment, and
   evidence attachment is recorded with actor and timestamp.
4. **Make experiments reproducible** — every detection run is tagged with a
   deterministic detector/dataset/feature version.

References: Tracer (C) case files, NEXUS (F) audit trail.

## Modules

### `backend/app/investigation.py`

Pure-logic investigation layer (no I/O — persistence is in `db.py`).

| Symbol | Purpose |
| --- | --- |
| `CaseStatus` | Enum: OBSERVED, SUSPICIOUS, HIGH_RISK, UNDER_REVIEW, CONFIRMED, DISMISSED, RESOLVED. |
| `CasePriority` | Enum: LOW, MEDIUM, HIGH, CRITICAL. |
| `compute_priority` | Deterministic priority from score, member count, typology. |
| `valid_transition` | Checks whether a lifecycle transition is allowed. |
| `CaseEvent` | A single lifecycle event (status change, note, assignment, evidence). |
| `InvestigationCase` | The case object: status, priority, members, score, typology, notes, evidence, events, versions. |
| `CaseManager` | In-memory manager: create, transition, note, evidence, assign, timeline, list, summary. |
| `auto_create_cases` | Auto-creates/updates cases from detection candidates above threshold. |

### Lifecycle state machine

```
OBSERVED ──► SUSPICIOUS ──► HIGH_RISK ──► UNDER_REVIEW ──► CONFIRMED
   │             │             │              │
   └──► DISMISSED ◄────────────┴──────────────┘
                                              └──► RESOLVED
```

- **Terminal states** (no further transitions): CONFIRMED, DISMISSED, RESOLVED.
- **Auto-escalation**: a case created with score ≥ 80 starts at HIGH_RISK
  instead of OBSERVED.
- **Priority rules**:
  - score ≥ 80, OR (high-risk typology AND score ≥ 65) → CRITICAL
  - score ≥ 65 OR members ≥ 10 → HIGH
  - score ≥ 55 → MEDIUM
  - else → LOW

### `backend/app/versions.py`

Deterministic versioning for reproducibility.

| Symbol | Purpose |
| --- | --- |
| `DetectorVersion` | Hash of signal weights + threshold + features. |
| `DatasetVersion` | Hash of dataset config (n_users, n_tx, n_rings, seed). |
| `FeatureVersion` | Hash of enabled feature set. |
| `RunVersion` | Combined hash of all three. |
| `log_versions` | JSON-serializable dict for audit logging. |

All hashes are SHA-256 truncated to 12 hex chars, computed over
sort-keyed JSON so they are stable across runs and platforms.

### `backend/app/db.py` (enhanced)

- `CaseRecord` — persistent case table (case_id, ring_id, status, priority,
  members, score, typology, assigned_to, notes, evidence, versions).
- `CaseEventRecord` — persistent event timeline.
- `AuditLog` — extended with `actor`, `ring_id`, `case_id`, `detector_version`.
- `save_case`, `save_case_event`, `get_cases`, `get_case_events`.

### `backend/app/main.py` (integrated)

- Auto-creates investigation cases whenever detection runs and a candidate
  crosses the threshold.
- New REST endpoints:
  - `GET /api/cases` — list cases (optional `?status=` filter) + summary
  - `GET /api/cases/{case_id}` — case detail + timeline
  - `POST /api/cases/{case_id}/transition` — lifecycle transition
  - `POST /api/cases/{case_id}/note` — add a note
  - `POST /api/cases/{case_id}/assign` — assign to an analyst
  - `GET /api/versions` — current detector/dataset/feature/run versions

## Regression Baseline

The Stage 3/4 regression baseline is **preserved** after Stage 5:

| Metric | Value |
| --- | --- |
| Top candidate score | 74.4 |
| Threshold | 55.0 |
| Precision | 1.000 |
| Recall | 0.263 |
| F1 | 0.417 |

## Test Coverage

- `backend/tests/test_investigation.py` — 55 tests (versioning, priority,
  state machine, CaseManager, auto-create).
- Full suite: **143 tests pass** (88 prior + 55 new).

## Usage

```python
from app.investigation import CaseManager, CaseStatus, auto_create_cases
from app.versions import DETECTOR_VERSION, DATASET_VERSION

cm = CaseManager()
cases = auto_create_cases(cm, candidates, score_threshold=55.0,
                          detector_version=DETECTOR_VERSION.hash,
                          dataset_version=DATASET_VERSION.hash)

case = cases[0]
cm.transition(case.case_id, CaseStatus.SUSPICIOUS, actor="analyst1")
cm.transition(case.case_id, CaseStatus.HIGH_RISK)
cm.transition(case.case_id, CaseStatus.UNDER_REVIEW)
cm.transition(case.case_id, CaseStatus.CONFIRMED)
print(cm.get_timeline(case.case_id))
```
