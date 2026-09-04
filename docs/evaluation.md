# Evaluation & Adversarial Testing

Offline evaluation harness and adversarial (evasion) testing. Complements
[`architecture.md`](./architecture.md) and [`dataset.md`](./dataset.md).

## Goals

1. **Go beyond single-point precision/recall** — threshold sweeps, PR-AUC /
   ROC-AUC, and baseline comparisons so the operating point is chosen
   deliberately.
2. **Measure temporal robustness** — does detection hold up when rings form
   in one period and are evaluated on a later period?
3. **Verify explanation faithfulness** — do the deterministic explanations
   reflect the features that drove the score?

## Modules

### `backend/app/evaluation.py`

Pure, deterministic offline evaluation functions.

| Function | Purpose |
|---|---|
| `threshold_sweep` | Sweep thresholds 10–95, compute per-threshold TP/FP/FN/TN, precision, recall, F1, FPR, TPR; returns PR-AUC, ROC-AUC, F1-optimal threshold |
| `random_baseline` | Uniform random scoring (seeded) |
| `degree_baseline` | Score = normalized in+out degree |
| `rule_based_baseline` | Score = volume + counterparty-count heuristics |
| `graph_detector_baseline` | Full graph detector as reference |
| `compare_all_baselines` | Runs all four baselines, sorted by F1 |
| `temporal_split_eval` | 70/30 timestamp split, train/test metrics + decay rate |
| `held_out_ring_eval` | Train on some rings, evaluate on held-out rings |
| `check_faithfulness` | Verifies explanation features are consistent with score |
| `generate_eval_report` | Comprehensive `EvalReport` combining all of the above |

### `backend/app/adversarial.py`

Generates perturbed fraud rings and measures detection degradation. 8
evasion variations:

| # | Variation | What it perturbs |
|---|---|---|
| 1 | Frequency | More/fewer transactions within the ring |
| 2 | Timing | Spread transactions over hours instead of minutes |
| 3 | External edges | Ring members transact with many innocent users |
| 4 | Innocent members | Mix non-fraud users into the ring's community |
| 5 | Ring size | Test detection at 3, 5, 10, 15, 20 members |
| 6 | Cycle-breaking | Remove one critical edge to break the loop |
| 7 | Amount variation | Make amounts vary wildly |
| 8 | Spread | Geographically spread ring members across cities |

Each variation produces a perturbed `(users, transactions, ground_truth)`
tuple that feeds directly into the detection pipeline. Results are
aggregated into a `RobustnessReport` with average/max score drop, worst
evasion, best robustness, and pass rate.

## Regression Baseline

| Metric | Value |
|---|---|
| Top candidate score | 74.4 |
| Threshold | 55.0 |
| Precision | 1.000 |
| Recall | 0.263 |
| F1 | 0.417 |

The 197-member background community (shared-IP campus/office cohort) scores
50.4 — below threshold — while the true 5-member ring scores 74.4.

## Test Coverage

- `backend/tests/test_evaluation.py` — 35 tests (threshold sweep, baselines,
  temporal split, held-out rings, faithfulness, report generation).

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
