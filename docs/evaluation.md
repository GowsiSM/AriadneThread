# Evaluation & Adversarial Testing (Stage 4)

This document describes the offline evaluation harness and adversarial
(evasion) testing added in Stage 4. It complements the existing
[`architecture.md`](./architecture.md) and [`dataset.md`](./dataset.md).

## Goals

1. **Go beyond single-point precision/recall** — provide threshold sweeps,
   PR-AUC / ROC-AUC, and baseline comparisons so the detector's operating
   point can be chosen deliberately.
2. **Measure temporal robustness** — does detection hold up when rings form
   in one period and are evaluated on a later period?
3. **Verify explanation faithfulness** — do the deterministic explanations
   actually reflect the features that drove the score?

## Modules

### `backend/app/evaluation.py`

Pure, deterministic offline evaluation functions.

| Function                                        | Purpose                                                                                                                                                             |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `threshold_sweep`                               | Sweep thresholds 10–95, compute per-threshold TP/FP/FN/TN, precision, recall, F1, FPR, TPR; returns PR-AUC and ROC-AUC (trapezoidal) plus the F1-optimal threshold. |
| `random_baseline`                               | Uniform random scoring (seeded).                                                                                                                                    |
| `degree_baseline`                               | Score = normalized in+out degree.                                                                                                                                   |
| `rule_based_baseline`                           | Score = volume heuristic + counterparty-count heuristic.                                                                                                            |
| `graph_detector_baseline`                       | Our full graph detector as the reference baseline.                                                                                                                  |
| `compare_all_baselines`                         | Runs all four baselines, sorted by F1 descending.                                                                                                                   |
| `temporal_split_eval`                           | Splits transactions 70/30 by timestamp, runs detection on each period, reports train/test metrics and a decay rate.                                                 |
| `held_out_ring_eval`                            | Trains on some rings, evaluates on held-out rings.                                                                                                                  |
| `check_faithfulness` / `check_all_faithfulness` | Verifies that each candidate's explanation features are consistent with the score.                                                                                  |
| `generate_eval_report`                          | Produces a comprehensive `EvalReport` combining all of the above.                                                                                                   |

### `backend/app/adversarial.py`

Generates perturbed versions of fraud rings and measures detection
degradation. 8 evasion variations from the brief (Section 3.8):

| #   | Variation        | What it perturbs                                    |
| --- | ---------------- | --------------------------------------------------- |
| 1   | Frequency        | More/fewer transactions within the ring             |
| 2   | Timing           | Spread transactions over hours instead of minutes   |
| 3   | External edges   | Ring members transact with many innocent users      |
| 4   | Innocent members | Mix non-fraud users into the ring's community       |
| 5   | Ring size        | Test detection at 3, 5, 10, 15, 20 members          |
| 6   | Cycle-breaking   | Remove one critical edge to break the loop          |
| 7   | Amount variation | Make amounts vary wildly (break amount fingerprint) |
| 8   | Spread           | Geographically spread ring members across cities    |

Each variation produces a perturbed `(users, transactions, ground_truth)`
tuple that feeds directly into the detection pipeline. Results are
aggregated into a `RobustnessReport` with average/max score drop, worst
evasion, best robustness, and a pass rate (fraction of variations where
detection was maintained above threshold).

## Regression Baseline

The Stage 3 regression baseline is **preserved** after Stage 4:

| Metric              | Value |
| ------------------- | ----- |
| Top candidate score | 74.4  |
| Threshold           | 55.0  |
| Precision           | 1.000 |
| Recall              | 0.263 |
| F1                  | 0.417 |

The 197-member background community (shared-IP campus/office cohort) scores
50.4 — below threshold — while the true 5-member ring scores 74.4.

## Test Coverage

- `backend/tests/test_evaluation.py` — 35 tests (threshold sweep, baselines,
  temporal split, held-out rings, faithfulness, report generation).
- Full suite: **88 tests pass** (21 original + 32 graph intelligence + 35
  evaluation).

## Usage

```python
from app.evaluation import generate_eval_report
from app.graph_engine import TransactionGraph
from app import data_gen

users, transactions = data_gen.generate_dataset(seed=1)
g = TransactionGraph()
for tx in transactions:
    g.add_transaction(tx)
user_index = {u.user_id: u for u in users}

report = generate_eval_report(g.snapshot(), g.shared_attribute_graph(user_index), user_index)
print(report.baselines)
print(report.sweep.pr_auc, report.sweep.roc_auc)
```

```python
from app.adversarial import run_adversarial_tests

report = run_adversarial_tests()
print(report.avg_score_drop, report.worst_evasion, report.pass_rate)
```
