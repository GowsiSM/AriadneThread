"""Tests for the deterministic synthetic AML/fraud dataset generator."""
import pytest

from app.synthetic import (
    generate_dataset,
    TYPOLOGIES,
    Dataset,
)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(
        n_background_users=150,
        n_background_tx=500,
        n_rings=12,
        seed=1,
    )


def test_dataset_schema(dataset):
    """Transactions and users have the expected schema fields."""
    assert isinstance(dataset, Dataset)
    assert dataset.transactions
    assert dataset.users
    for t in dataset.transactions:
        assert t.tx_id
        assert t.sender
        assert t.receiver
        assert t.amount > 0
        assert t.currency == "INR"
    for u in dataset.users:
        assert u.user_id
        assert u.device_id
        assert u.ip_address


def test_all_typologies_present(dataset):
    """With 12 rings, all 12 typologies should be represented."""
    typologies = {s.typology for s in dataset.scenarios}
    assert typologies == set(TYPOLOGIES)


def test_ground_truth_metadata(dataset):
    """Each scenario has complete ground-truth metadata."""
    for s in dataset.scenarios:
        assert s.scenario_id
        assert s.typology in TYPOLOGIES
        assert len(s.fraud_users) >= 3
        assert s.start_time <= s.end_time
        assert s.expected_detection is True
        assert s.roles  # non-empty role map


def test_no_label_leakage_in_transactions(dataset):
    """Ground-truth columns must not be present in the detector-facing
    transaction export. The export script strips is_fraud_ring_member,
    ring_id, typology, and role from the CSV."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    from generate_synthetic_fraud import _strip_ground_truth

    for t in dataset.transactions:
        d = _strip_ground_truth(t.to_dict())
        assert "is_fraud_ring_member" not in d
        assert "ring_id" not in d
        assert "typology" not in d
        assert "role" not in d


def test_deterministic_with_seed():
    d1 = generate_dataset(n_background_users=50, n_background_tx=100, n_rings=4, seed=99)
    d2 = generate_dataset(n_background_users=50, n_background_tx=100, n_rings=4, seed=99)
    assert [t.tx_id for t in d1.transactions] == [t.tx_id for t in d2.transactions]
    assert [u.user_id for u in d1.users] == [u.user_id for u in d2.users]
    assert [s.scenario_id for s in d1.scenarios] == [s.scenario_id for s in d2.scenarios]


def test_transactions_sorted_by_time(dataset):
    ts = [t.ts for t in dataset.transactions]
    assert ts == sorted(ts)


def test_fraud_users_are_labeled(dataset):
    fraud_ids = {t.ring_id for t in dataset.transactions if t.is_fraud_ring_member}
    assert len(fraud_ids) == len(dataset.scenarios)
    # Every scenario's users appear in the transaction stream as fraud members.
    for s in dataset.scenarios:
        assert any(t.ring_id == s.scenario_id for t in dataset.transactions)


def test_meta_versioning(dataset):
    assert dataset.meta["dataset_version"] == "synthetic-aml-v1"
    assert dataset.meta["n_rings"] == len(dataset.scenarios)
    assert dataset.meta["n_transactions"] == len(dataset.transactions)
