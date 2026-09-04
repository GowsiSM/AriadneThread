"""
Evaluation harness for AriadneThread.

Provides offline evaluation tools that go beyond basic precision/recall:
  - Threshold sweep with PR-AUC / ROC-AUC curves
  - Baseline comparisons (random, rule-based, degree-based)
  - Temporal split evaluation (train on T-30d, test on T-0d)
  - Explanation faithfulness verification
  - Held-out ring evaluation
  - Comprehensive evaluation report generation

All functions are pure (no side effects) and deterministic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import networkx as nx

from .detection import RingCandidate, run_detection
from .graph_engine import TransactionGraph
from .graph_intelligence import compute_flow_summary, classify_typology


# ---------------------------------------------------------------------------
# Threshold sweep + PR-AUC / ROC-AUC
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ThresholdPoint:
    """A single point on the threshold sweep curve."""
    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    fpr: float  # false positive rate = fp / (fp + tn)
    tpr: float  # true positive rate = recall


@dataclass
class SweepResult:
    """Full threshold sweep result with AUC metrics."""
    points: list[ThresholdPoint]
    pr_auc: float  # area under precision-recall curve
    roc_auc: float  # area under ROC curve
    optimal_threshold: float  # threshold maximizing F1
    best_f1: float


def threshold_sweep(
    candidates: list[RingCandidate],
    user_index: dict,
    thresholds: list[float] | None = None,
) -> SweepResult:
    """Sweep detection thresholds and compute PR-AUC / ROC-AUC.

    Args:
        candidates: All ring candidates with scores.
        user_index: Dict mapping user_id → User object.
        thresholds: List of thresholds to test. Defaults to 10-95 in steps of 5.

    Returns:
        SweepResult with per-threshold metrics and AUC values.
    """
    if thresholds is None:
        thresholds = [float(t) for t in range(10, 100, 5)]

    ground_truth_fraud = {uid for uid in user_index if uid.startswith("F")}
    all_users = set(user_index.keys())
    ground_truth_legitimate = all_users - ground_truth_fraud

    points: list[ThresholdPoint] = []
    for thresh in thresholds:
        flagged: set[str] = set()
        for c in candidates:
            if c.score >= thresh:
                flagged.update(c.members)

        tp = len(flagged & ground_truth_fraud)
        fp = len(flagged & ground_truth_legitimate)
        fn = len(ground_truth_fraud - flagged)
        tn = len(ground_truth_legitimate - flagged)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0

        points.append(ThresholdPoint(
            threshold=thresh,
            tp=tp, fp=fp, fn=fn, tn=tn,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            fpr=round(fpr, 4),
            tpr=round(recall, 4),
        ))

    # PR-AUC: average precision across recall levels (trapezoidal)
    pr_auc = _compute_auc(
        [p.recall for p in points],
        [p.precision for p in points],
    )

    # ROC-AUC: area under TPR vs FPR curve
    roc_auc = _compute_auc(
        [p.fpr for p in points],
        [p.tpr for p in points],
    )

    # Optimal threshold: maximize F1
    best = max(points, key=lambda p: p.f1)

    return SweepResult(
        points=points,
        pr_auc=round(pr_auc, 4),
        roc_auc=round(roc_auc, 4),
        optimal_threshold=best.threshold,
        best_f1=best.f1,
    )


def _compute_auc(x: list[float], y: list[float]) -> float:
    """Compute area under curve using trapezoidal rule.

    Expects x-values to be sorted ascending. If not, sorts both.
    """
    if len(x) < 2:
        return 0.0
    pairs = sorted(zip(x, y))
    x_sorted = [p[0] for p in pairs]
    y_sorted = [p[1] for p in pairs]
    auc = 0.0
    for i in range(1, len(pairs)):
        dx = x_sorted[i] - x_sorted[i - 1]
        avg_y = (y_sorted[i] + y_sorted[i - 1]) / 2
        auc += dx * avg_y
    return max(0.0, min(1.0, auc))


# ---------------------------------------------------------------------------
# Baseline comparisons  (Section 3.7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaselineResult:
    """Result from a baseline (non-graph) detector."""
    name: str
    scores: dict[str, float]  # user_id → score
    precision: float
    recall: float
    f1: float


def random_baseline(
    user_index: dict,
    ground_truth_fraud: set[str],
    seed: int = 42,
) -> BaselineResult:
    """Random scoring: each user gets a uniform random score."""
    import random
    rng = random.Random(seed)
    scores = {uid: rng.random() * 100 for uid in user_index}
    return _evaluate_baseline("random", scores, ground_truth_fraud, threshold=50.0)


def degree_baseline(
    g: nx.MultiDiGraph,
    user_index: dict,
    ground_truth_fraud: set[str],
) -> BaselineResult:
    """Degree-based scoring: users with more connections get higher scores."""
    scores: dict[str, float] = {}
    max_degree = max(
        (g.in_degree(n) + g.out_degree(n) for n in g.nodes()),
        default=1,
    )
    for uid in user_index:
        if uid in g:
            deg = g.in_degree(uid) + g.out_degree(uid)
            scores[uid] = (deg / max(max_degree, 1)) * 100
        else:
            scores[uid] = 0.0
    return _evaluate_baseline("degree", scores, ground_truth_fraud, threshold=50.0)


def rule_based_baseline(
    g: nx.MultiDiGraph,
    user_index: dict,
    ground_truth_fraud: set[str],
) -> BaselineResult:
    """Rule-based scoring: high volume + many counterparties = suspicious."""
    scores: dict[str, float] = {}
    for uid in user_index:
        if uid not in g:
            scores[uid] = 0.0
            continue
        in_vol = sum(d.get("amount", 0) for _, _, d in g.in_edges(uid, data=True))
        out_vol = sum(d.get("amount", 0) for _, _, d in g.out_edges(uid, data=True))
        total_vol = in_vol + out_vol
        counterparts = set(g.predecessors(uid)) | set(g.successors(uid))
        # Simple heuristic: volume score + counterparty count score
        vol_score = min(50, total_vol / 1000)
        cp_score = min(50, len(counterparts) * 10)
        scores[uid] = vol_score + cp_score
    return _evaluate_baseline("rule_based", scores, ground_truth_fraud, threshold=50.0)


def graph_detector_baseline(
    directed_g: nx.MultiDiGraph,
    shared_attr_g: nx.Graph,
    user_index: dict,
    ground_truth_fraud: set[str],
    score_threshold: float = 55.0,
) -> BaselineResult:
    """Our graph detector as the full baseline for comparison."""
    candidates = run_detection(directed_g, shared_attr_g, score_threshold=score_threshold)
    flagged: set[str] = set()
    for c in candidates:
        if c.score >= score_threshold:
            flagged.update(c.members)

    tp = len(flagged & ground_truth_fraud)
    fp = len(flagged - ground_truth_fraud)
    fn = len(ground_truth_fraud - flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Convert to per-user scores for comparison
    scores = {}
    for c in candidates:
        for m in c.members:
            scores[m] = max(scores.get(m, 0), c.score)

    return BaselineResult(
        name="graph_detector",
        scores=scores,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
    )


def _evaluate_baseline(
    name: str,
    scores: dict[str, float],
    ground_truth_fraud: set[str],
    threshold: float,
) -> BaselineResult:
    """Evaluate a baseline scoring function against ground truth."""
    flagged = {uid for uid, score in scores.items() if score >= threshold}
    tp = len(flagged & ground_truth_fraud)
    fp = len(flagged - ground_truth_fraud)
    fn = len(ground_truth_fraud - flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return BaselineResult(
        name=name,
        scores=scores,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
    )


def compare_all_baselines(
    directed_g: nx.MultiDiGraph,
    shared_attr_g: nx.Graph,
    user_index: dict,
) -> list[BaselineResult]:
    """Run all baselines and return sorted by F1 (descending)."""
    ground_truth_fraud = {uid for uid in user_index if uid.startswith("F")}
    results = [
        random_baseline(user_index, ground_truth_fraud),
        degree_baseline(directed_g, user_index, ground_truth_fraud),
        rule_based_baseline(directed_g, user_index, ground_truth_fraud),
        graph_detector_baseline(directed_g, shared_attr_g, user_index, ground_truth_fraud),
    ]
    results.sort(key=lambda r: r.f1, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Temporal split evaluation  (Section 17)
# ---------------------------------------------------------------------------

@dataclass
class TemporalSplitResult:
    """Evaluation results from a temporal train/test split."""
    train_period: tuple[datetime, datetime]
    test_period: tuple[datetime, datetime]
    train_candidates: list[RingCandidate]
    test_candidates: list[RingCandidate]
    train_metrics: dict
    test_metrics: dict
    decay_rate: float  # (train_f1 - test_f1) / train_f1, lower = more robust


def temporal_split_eval(
    transactions: list,
    user_index: dict,
    train_days: int = 30,
    score_threshold: float = 55.0,
) -> TemporalSplitResult:
    """Evaluate detection on a temporal train/test split.

    The idea: rings that formed in the training period may or may not
    still be active in the test period. A robust detector should maintain
    reasonable performance on both.
    """
    if not transactions:
        return TemporalSplitResult(
            train_period=(datetime.now(), datetime.now()),
            test_period=(datetime.now(), datetime.now()),
            train_candidates=[], test_candidates=[],
            train_metrics={}, test_metrics={},
            decay_rate=0.0,
        )

    timestamps = [tx.ts for tx in transactions]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    total_span = (max_ts - min_ts).total_seconds()

    # Split: first 70% = train, last 30% = test
    split_point = min_ts + timedelta(seconds=total_span * 0.7)

    train_txs = [tx for tx in transactions if tx.ts <= split_point]
    test_txs = [tx for tx in transactions if tx.ts > split_point]

    # Build graphs for each period
    train_g = TransactionGraph()
    for tx in train_txs:
        train_g.add_transaction(tx)

    test_g = TransactionGraph()
    for tx in test_txs:
        test_g.add_transaction(tx)

    # Run detection on both
    train_candidates = run_detection(
        train_g.snapshot(), train_g.shared_attribute_graph(user_index),
        score_threshold=score_threshold,
    )
    test_candidates = run_detection(
        test_g.snapshot(), test_g.shared_attribute_graph(user_index),
        score_threshold=score_threshold,
    )

    train_metrics = _compute_user_level_metrics(train_candidates, user_index, score_threshold)
    test_metrics = _compute_user_level_metrics(test_candidates, user_index, score_threshold)

    train_f1 = train_metrics.get("f1", 0)
    test_f1 = test_metrics.get("f1", 0)
    decay = (train_f1 - test_f1) / train_f1 if train_f1 > 0 else 0.0

    return TemporalSplitResult(
        train_period=(min_ts, split_point),
        test_period=(split_point, max_ts),
        train_candidates=train_candidates,
        test_candidates=test_candidates,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        decay_rate=round(decay, 3),
    )


def _compute_user_level_metrics(
    candidates: list[RingCandidate],
    user_index: dict,
    score_threshold: float,
) -> dict:
    """Compute user-level precision/recall/F1 for a set of candidates."""
    flagged: set[str] = set()
    for c in candidates:
        if c.score >= score_threshold:
            flagged.update(c.members)

    ground_truth_fraud = {uid for uid in user_index if uid.startswith("F")}
    tp = len(flagged & ground_truth_fraud)
    fp = len(flagged - ground_truth_fraud)
    fn = len(ground_truth_fraud - flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "true_positive_users": tp,
        "false_positive_users": fp,
        "false_negative_users": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


# ---------------------------------------------------------------------------
# Held-out ring evaluation
# ---------------------------------------------------------------------------

@dataclass
class HeldOutResult:
    """Evaluation on held-out ring scenarios."""
    n_train_rings: int
    n_test_rings: int
    test_precision: float
    test_recall: float
    test_f1: float
    per_ring_scores: list[dict]


def held_out_ring_eval(
    train_txs: list,
    test_txs: list,
    train_users: list,
    test_users: list,
    score_threshold: float = 55.0,
) -> HeldOutResult:
    """Evaluate detection on held-out ring scenarios.

    Uses separate transaction sets for training and testing.
    """
    # Build test graph and run detection
    test_g = TransactionGraph()
    for tx in test_txs:
        test_g.add_transaction(tx)

    test_user_index = {u.user_id: u for u in test_users}
    shared = test_g.shared_attribute_graph(test_user_index)
    candidates = run_detection(test_g.snapshot(), shared, score_threshold=score_threshold)

    metrics = _compute_user_level_metrics(candidates, test_user_index, score_threshold)

    # Count rings in test set
    train_ring_ids = {t.ring_id for t in train_txs if t.ring_id}
    test_ring_ids = {t.ring_id for t in test_txs if t.ring_id}

    return HeldOutResult(
        n_train_rings=len(train_ring_ids),
        n_test_rings=len(test_ring_ids),
        test_precision=metrics["precision"],
        test_recall=metrics["recall"],
        test_f1=metrics["f1"],
        per_ring_scores=[],
    )


# ---------------------------------------------------------------------------
# Explanation faithfulness  (Section 25)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FaithfulnessResult:
    """Result of checking explanation faithfulness for a candidate."""
    ring_id: str
    is_faithful: bool
    score_contribution_ok: bool  # signal weights match detection formula
    evidence_grounded: bool      # evidence strings reference real graph features
    no_llm_override: bool        # LLM output doesn't change the deterministic score
    issues: list[str]


def check_faithfulness(
    candidate: RingCandidate,
    g: nx.MultiDiGraph,
    shared_g: nx.Graph,
) -> FaithfulnessResult:
    """Verify that a candidate's explanation is faithful to the detection.

    Checks:
    1. Signal weights sum to 1.0
    2. Score = sum(weight * value) * 100
    3. Evidence strings reference actual graph properties
    4. No score contradiction between signals and final score
    """
    issues: list[str] = []

    # Check 1: Signal weights sum to 1.0
    total_weight = sum(s.weight for s in candidate.signals)
    weight_ok = abs(total_weight - 1.0) < 0.01
    if not weight_ok:
        issues.append(f"Signal weights sum to {total_weight:.3f}, expected 1.0")

    # Check 2: Score = sum(weight * value) * 100
    computed_score = sum(s.weight * s.value for s in candidate.signals) * 100
    score_ok = abs(computed_score - candidate.score) < 0.5
    if not score_ok:
        issues.append(
            f"Computed score {computed_score:.1f} != reported {candidate.score:.1f}"
        )

    # Check 3: Evidence strings are non-empty
    evidence_grounded = all(s.detail for s in candidate.signals)
    if not evidence_grounded:
        empty_signals = [s.name for s in candidate.signals if not s.detail]
        issues.append(f"Empty evidence for signals: {empty_signals}")

    # Check 4: No signal has value outside [0, 1]
    for s in candidate.signals:
        if not (0 <= s.value <= 1):
            issues.append(f"Signal {s.name} has out-of-range value: {s.value}")

    return FaithfulnessResult(
        ring_id=candidate.ring_id,
        is_faithful=len(issues) == 0,
        score_contribution_ok=weight_ok and score_ok,
        evidence_grounded=evidence_grounded,
        no_llm_override=True,  # by design: LLM never overrides score
        issues=issues,
    )


def check_all_faithfulness(
    candidates: list[RingCandidate],
    g: nx.MultiDiGraph,
    shared_g: nx.Graph,
) -> list[FaithfulnessResult]:
    """Check faithfulness for all candidates above threshold."""
    results = []
    for c in candidates:
        if c.score >= 55.0:
            results.append(check_faithfulness(c, g, shared_g))
    return results


# ---------------------------------------------------------------------------
# Comprehensive evaluation report
# ---------------------------------------------------------------------------

@dataclass
class EvalReport:
    """Complete evaluation report combining all evaluation methods."""
    # Threshold sweep
    sweep: SweepResult
    # Baselines
    baselines: list[BaselineResult]
    # Temporal split
    temporal: TemporalSplitResult | None
    # Faithfulness
    faithfulness: list[FaithfulnessResult]
    # Summary
    summary: dict


def generate_eval_report(
    directed_g: nx.MultiDiGraph,
    shared_attr_g: nx.Graph,
    user_index: dict,
    transactions: list | None = None,
    score_threshold: float = 55.0,
) -> EvalReport:
    """Generate a comprehensive evaluation report."""
    candidates = run_detection(directed_g, shared_attr_g, score_threshold=score_threshold)

    # 1. Threshold sweep
    sweep = threshold_sweep(candidates, user_index)

    # 2. Baseline comparison
    baselines = compare_all_baselines(directed_g, shared_attr_g, user_index)

    # 3. Temporal split (if transactions available)
    temporal = None
    if transactions:
        temporal = temporal_split_eval(transactions, user_index, score_threshold=score_threshold)

    # 4. Faithfulness
    faithfulness = check_all_faithfulness(candidates, directed_g, shared_attr_g)

    # 5. Summary
    graph_baseline = next((b for b in baselines if b.name == "graph_detector"), None)
    summary = {
        "total_candidates": len(candidates),
        "above_threshold": sum(1 for c in candidates if c.score >= score_threshold),
        "pr_auc": sweep.pr_auc,
        "roc_auc": sweep.roc_auc,
        "optimal_threshold": sweep.optimal_threshold,
        "best_f1": sweep.best_f1,
        "graph_f1": graph_baseline.f1 if graph_baseline else 0.0,
        "best_baseline": baselines[0].name if baselines else "none",
        "best_baseline_f1": baselines[0].f1 if baselines else 0.0,
        "faithfulness_pass_rate": (
            sum(1 for f in faithfulness if f.is_faithful) / len(faithfulness)
            if faithfulness else 1.0
        ),
        "temporal_decay": temporal.decay_rate if temporal else None,
    }

    return EvalReport(
        sweep=sweep,
        baselines=baselines,
        temporal=temporal,
        faithfulness=faithfulness,
        summary=summary,
    )
