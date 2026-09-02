import networkx as nx
import pytest

from app import data_gen
from app.detection import run_detection
from app.fairness import precision_recall, compute_cohort_fp_stats, compute_blast_radius
from app.graph_engine import TransactionGraph


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


def test_dataset_has_labeled_rings(dataset):
    users, transactions = dataset
    ring_ids = {t.ring_id for t in transactions if t.is_fraud_ring_member}
    assert len(ring_ids) == 3
    fraud_users = [u for u in users if u.user_id.startswith("F")]
    assert len(fraud_users) >= 15  # 3 rings * ~5-9 members


def test_dataset_is_deterministic_with_seed():
    u1, t1 = data_gen.generate_dataset(n_background_users=50, n_background_tx=100, n_rings=2, seed=99)
    u2, t2 = data_gen.generate_dataset(n_background_users=50, n_background_tx=100, n_rings=2, seed=99)
    assert [u.user_id for u in u1] == [u.user_id for u in u2]
    assert [t.tx_id for t in t1] == [t.tx_id for t in t2]


def test_graph_builds_without_errors(built_graph):
    assert built_graph.graph.number_of_nodes() > 0
    assert built_graph.edge_count > 0


def test_detection_finds_at_least_one_high_score_ring(dataset, built_graph):
    users, transactions = dataset
    user_index = {u.user_id: u for u in users}
    shared = built_graph.shared_attribute_graph(user_index)
    candidates = run_detection(built_graph.snapshot(), shared, score_threshold=55.0)
    assert len(candidates) > 0
    top = candidates[0]
    assert top.score > 0
    # at least one candidate should substantially overlap a real ring
    fraud_users = {u.user_id for u in users if u.user_id.startswith("F")}
    best_overlap = max(
        len(set(c.members) & fraud_users) / max(1, len(c.members)) for c in candidates
    )
    assert best_overlap > 0.3


def test_detection_scores_are_bounded(dataset, built_graph):
    users, transactions = dataset
    user_index = {u.user_id: u for u in users}
    shared = built_graph.shared_attribute_graph(user_index)
    candidates = run_detection(built_graph.snapshot(), shared)
    for c in candidates:
        assert 0.0 <= c.score <= 100.0


def test_precision_recall_reasonable(dataset, built_graph):
    users, transactions = dataset
    user_index = {u.user_id: u for u in users}
    shared = built_graph.shared_attribute_graph(user_index)
    candidates = run_detection(built_graph.snapshot(), shared, score_threshold=55.0)
    metrics = precision_recall(candidates, user_index, 55.0)
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    # detector should catch a meaningful share of planted fraud users
    assert metrics["recall"] > 0.2


def test_cohort_fp_stats_cover_all_cohorts(dataset, built_graph):
    users, transactions = dataset
    user_index = {u.user_id: u for u in users}
    shared = built_graph.shared_attribute_graph(user_index)
    candidates = run_detection(built_graph.snapshot(), shared, score_threshold=55.0)
    stats = compute_cohort_fp_stats(candidates, user_index, 55.0, {})
    seen_cohorts = {s.cohort for s in stats}
    actual_cohorts = {u.cohort for u in users}
    assert seen_cohorts == actual_cohorts
    for s in stats:
        assert s.false_positives <= s.flagged_users <= s.total_users


def test_blast_radius_fields_sane(dataset, built_graph):
    users, transactions = dataset
    user_index = {u.user_id: u for u in users}
    shared = built_graph.shared_attribute_graph(user_index)
    candidates = run_detection(built_graph.snapshot(), shared, score_threshold=55.0)
    assert candidates, "expected at least one candidate to test blast radius on"
    blast = compute_blast_radius(candidates[0], user_index, {})
    assert 0.0 <= blast.innocent_ratio <= 1.0
    assert blast.total_members == len(candidates[0].members)
    assert blast.recommendation  # non-empty string


def test_empty_graph_does_not_crash():
    g = nx.MultiDiGraph()
    shared = nx.Graph()
    candidates = run_detection(g, shared)
    assert candidates == []
