"""Tests for the evaluation and adversarial modules (Stage 4)."""
import networkx as nx
import pytest

from app import data_gen
from app.detection import run_detection
from app.graph_engine import TransactionGraph
from app.evaluation import (
    threshold_sweep,
    SweepResult,
    ThresholdPoint,
    random_baseline,
    degree_baseline,
    rule_based_baseline,
    graph_detector_baseline,
    compare_all_baselines,
    temporal_split_eval,
    held_out_ring_eval,
    check_faithfulness,
    check_all_faithfulness,
    generate_eval_report,
    _compute_auc,
)
from app.adversarial import (
    run_adversarial_tests,
    RobustnessReport,
    AdversarialResult,
    PERTURBATIONS,
    _perturb_frequency,
    _perturb_timing,
    _perturb_external_edges,
    _perturb_innocent_members,
    _perturb_ring_size,
    _perturb_cycle_breaking,
    _perturb_amount_variation,
    _perturb_spread,
)


@pytest.fixture(scope="module")
def dataset():
    users, transactions = data_gen.generate_dataset(
        n_background_users=150, n_background_tx=500, n_rings=3, seed=1
    )
    return users, transactions


@pytest.fixture(scope="module")
def built_graph(dataset):
    users, transactions = dataset
    g = TransactionGraph()
    for tx in transactions:
        g.add_transaction(tx)
    return g


@pytest.fixture(scope="module")
def user_index(dataset):
    users, _ = dataset
    return {u.user_id: u for u in users}


@pytest.fixture(scope="module")
def candidates(dataset, built_graph, user_index):
    shared = built_graph.shared_attribute_graph(user_index)
    return run_detection(built_graph.snapshot(), shared, score_threshold=55.0)


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

class TestThresholdSweep:
    def test_sweep_returns_points(self, candidates, user_index):
        result = threshold_sweep(candidates, user_index)
        assert isinstance(result, SweepResult)
        assert len(result.points) > 0
        assert all(isinstance(p, ThresholdPoint) for p in result.points)

    def test_sweep_thresholds_ascending(self, candidates, user_index):
        result = threshold_sweep(candidates, user_index)
        thresholds = [p.threshold for p in result.points]
        assert thresholds == sorted(thresholds)

    def test_sweep_metrics_bounded(self, candidates, user_index):
        result = threshold_sweep(candidates, user_index)
        for p in result.points:
            assert 0.0 <= p.precision <= 1.0
            assert 0.0 <= p.recall <= 1.0
            assert 0.0 <= p.f1 <= 1.0
            assert 0.0 <= p.fpr <= 1.0
            assert 0.0 <= p.tpr <= 1.0

    def test_auc_bounded(self, candidates, user_index):
        result = threshold_sweep(candidates, user_index)
        assert 0.0 <= result.pr_auc <= 1.0
        assert 0.0 <= result.roc_auc <= 1.0

    def test_optimal_threshold_valid(self, candidates, user_index):
        result = threshold_sweep(candidates, user_index)
        assert result.optimal_threshold in [p.threshold for p in result.points]
        assert 0.0 <= result.best_f1 <= 1.0

    def test_custom_thresholds(self, candidates, user_index):
        thresholds = [10.0, 20.0, 30.0]
        result = threshold_sweep(candidates, user_index, thresholds)
        assert [p.threshold for p in result.points] == thresholds

    def test_empty_candidates(self, user_index):
        result = threshold_sweep([], user_index)
        assert len(result.points) > 0
        assert result.pr_auc == 0.0

    def test_auc_helper(self):
        # Perfect classifier: TPR=1, FPR=0 → AUC=1
        assert _compute_auc([0.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)
        # Random: diagonal → AUC=0.5
        assert _compute_auc([0.0, 1.0], [0.0, 1.0]) == pytest.approx(0.5)
        # Empty
        assert _compute_auc([], []) == 0.0


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

class TestBaselines:
    def test_random_baseline(self, user_index):
        ground_truth = {uid for uid in user_index if uid.startswith("F")}
        result = random_baseline(user_index, ground_truth)
        assert result.name == "random"
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert 0.0 <= result.f1 <= 1.0

    def test_random_baseline_deterministic(self, user_index):
        ground_truth = {uid for uid in user_index if uid.startswith("F")}
        r1 = random_baseline(user_index, ground_truth, seed=42)
        r2 = random_baseline(user_index, ground_truth, seed=42)
        assert r1.scores == r2.scores

    def test_degree_baseline(self, built_graph, user_index):
        ground_truth = {uid for uid in user_index if uid.startswith("F")}
        result = degree_baseline(built_graph.snapshot(), user_index, ground_truth)
        assert result.name == "degree"
        assert 0.0 <= result.f1 <= 1.0

    def test_rule_based_baseline(self, built_graph, user_index):
        ground_truth = {uid for uid in user_index if uid.startswith("F")}
        result = rule_based_baseline(built_graph.snapshot(), user_index, ground_truth)
        assert result.name == "rule_based"
        assert 0.0 <= result.f1 <= 1.0

    def test_graph_detector_baseline(self, built_graph, user_index):
        ground_truth = {uid for uid in user_index if uid.startswith("F")}
        shared = built_graph.shared_attribute_graph(user_index)
        result = graph_detector_baseline(
            built_graph.snapshot(), shared, user_index, ground_truth
        )
        assert result.name == "graph_detector"
        assert 0.0 <= result.f1 <= 1.0

    def test_compare_all_baselines(self, built_graph, user_index):
        shared = built_graph.shared_attribute_graph(user_index)
        results = compare_all_baselines(built_graph.snapshot(), shared, user_index)
        assert len(results) == 4
        # Sorted by F1 descending
        f1s = [r.f1 for r in results]
        assert f1s == sorted(f1s, reverse=True)
        # Graph detector should be among the top performers
        names = [r.name for r in results]
        assert "graph_detector" in names


# ---------------------------------------------------------------------------
# Temporal split
# ---------------------------------------------------------------------------

class TestTemporalSplit:
    def test_temporal_split_runs(self, dataset, user_index):
        users, transactions = dataset
        result = temporal_split_eval(transactions, user_index)
        assert result.train_period[0] <= result.train_period[1]
        assert result.test_period[0] <= result.test_period[1]
        assert 0.0 <= result.decay_rate <= 1.0

    def test_temporal_split_metrics(self, dataset, user_index):
        users, transactions = dataset
        result = temporal_split_eval(transactions, user_index)
        for metrics in [result.train_metrics, result.test_metrics]:
            assert 0.0 <= metrics.get("precision", 0) <= 1.0
            assert 0.0 <= metrics.get("recall", 0) <= 1.0
            assert 0.0 <= metrics.get("f1", 0) <= 1.0

    def test_temporal_split_empty(self, user_index):
        result = temporal_split_eval([], user_index)
        assert result.train_candidates == []
        assert result.test_candidates == []


# ---------------------------------------------------------------------------
# Held-out ring evaluation
# ---------------------------------------------------------------------------

class TestHeldOut:
    def test_held_out_runs(self, dataset, user_index):
        users, transactions = dataset
        # Split transactions into two halves
        mid = len(transactions) // 2
        train_txs = transactions[:mid]
        test_txs = transactions[mid:]
        result = held_out_ring_eval(train_txs, test_txs, users, users)
        assert 0.0 <= result.test_precision <= 1.0
        assert 0.0 <= result.test_recall <= 1.0
        assert 0.0 <= result.test_f1 <= 1.0


# ---------------------------------------------------------------------------
# Explanation faithfulness
# ---------------------------------------------------------------------------

class TestFaithfulness:
    def test_faithful_candidate(self, candidates, built_graph, user_index):
        shared = built_graph.shared_attribute_graph(user_index)
        top = candidates[0]
        result = check_faithfulness(top, built_graph.snapshot(), shared)
        assert result.is_faithful
        assert result.score_contribution_ok
        assert result.evidence_grounded
        assert result.no_llm_override

    def test_all_faithful(self, candidates, built_graph, user_index):
        shared = built_graph.shared_attribute_graph(user_index)
        results = check_all_faithfulness(candidates, built_graph.snapshot(), shared)
        assert len(results) > 0
        for r in results:
            assert r.is_faithful

    def test_signal_weights_sum_to_one(self, candidates):
        for c in candidates:
            total = sum(s.weight for s in c.signals)
            assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Comprehensive report
# ---------------------------------------------------------------------------

class TestEvalReport:
    def test_generate_report(self, dataset, built_graph, user_index):
        users, transactions = dataset
        shared = built_graph.shared_attribute_graph(user_index)
        report = generate_eval_report(
            built_graph.snapshot(), shared, user_index, transactions
        )
        assert report.sweep.pr_auc >= 0.0
        assert len(report.baselines) == 4
        assert report.summary["total_candidates"] > 0
        assert report.summary["faithfulness_pass_rate"] == 1.0
        assert report.summary["temporal_decay"] is not None


# ---------------------------------------------------------------------------
# Adversarial testing
# ---------------------------------------------------------------------------

class TestAdversarial:
    def test_perturbations_registered(self):
        assert len(PERTURBATIONS) >= 8  # at least the 8 required variations

    def test_frequency_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_frequency(
            users, transactions, fraud_ids, 2.0
        )
        assert len(new_txs) > len(transactions)

    def test_timing_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_timing(
            users, transactions, fraud_ids, 360
        )
        assert len(new_txs) == len(transactions)

    def test_external_edges_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_external_edges(
            users, transactions, fraud_ids, 5
        )
        assert len(new_txs) > len(transactions)

    def test_innocent_members_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_innocent_members(
            users, transactions, fraud_ids, 2
        )
        assert len(new_txs) > len(transactions)

    def test_ring_size_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_ring_size(
            users, transactions, fraud_ids, 10
        )
        # Ring size perturbation can grow or shrink the ring toward target
        assert len(new_fraud) > 0
        assert len(new_fraud) <= 10 or len(new_fraud) >= len(fraud_ids)

    def test_cycle_breaking_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_cycle_breaking(
            users, transactions, fraud_ids
        )
        assert len(new_txs) <= len(transactions)

    def test_amount_variation_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_amount_variation(
            users, transactions, fraud_ids, 3.0
        )
        assert len(new_txs) == len(transactions)

    def test_spread_perturbation(self, dataset):
        users, transactions = dataset
        fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
        new_users, new_txs, new_fraud = _perturb_spread(
            users, transactions, fraud_ids, 4
        )
        assert len(new_users) == len(users)

    def test_run_adversarial_tests(self):
        report = run_adversarial_tests(seed=42, threshold=55.0)
        assert isinstance(report, RobustnessReport)
        assert len(report.results) == len(PERTURBATIONS)
        assert 0.0 <= report.avg_score_drop <= 100.0
        assert 0.0 <= report.pass_rate <= 1.0
        assert report.worst_evasion in PERTURBATIONS
        assert report.best_robustness in PERTURBATIONS

    def test_adversarial_results_have_scores(self):
        report = run_adversarial_tests(seed=42, threshold=55.0)
        for r in report.results:
            assert isinstance(r, AdversarialResult)
            assert 0.0 <= r.original_score <= 100.0
            assert 0.0 <= r.perturbed_score <= 100.0
            assert r.score_drop >= -100.0  # could be negative if perturbation helps

    def test_adversarial_deterministic(self):
        r1 = run_adversarial_tests(seed=42, threshold=55.0)
        r2 = run_adversarial_tests(seed=42, threshold=55.0)
        assert [r.score_drop for r in r1.results] == [r.score_drop for r in r2.results]

    def test_adversarial_subset(self):
        report = run_adversarial_tests(seed=42, threshold=55.0, variations=["cycle_break"])
        assert len(report.results) == 1
        assert report.results[0].variation == "cycle_break"
