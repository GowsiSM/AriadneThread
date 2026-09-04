"""
Adversarial / evasion testing for AriadneThread.

Our unique differentiator: none of the 7 reference repos test robustness
to controlled fraud variations. This module generates perturbed versions
of fraud rings and measures how detection degrades under each evasion
strategy. 8 variations from the brief (Section 3.8):

  1. Frequency  — more/fewer transactions within the ring
  2. Timing     — spread transactions out over hours instead of minutes
  3. External edges — ring members transact with many innocent users
  4. Innocent members — mix non-fraud users into the ring's community
  5. Ring size  — test detection at 3, 5, 10, 15, 20 members
  6. Cycle-breaking — remove one critical edge to break the loop
  7. Amount variation — make amounts vary wildly (break amount fingerprint)
  8. Spread     — geographically spread ring members across cities

Each variation produces a perturbed (users, transactions, ground_truth)
tuple that can be fed directly into the detection pipeline.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import networkx as nx

from .detection import RingCandidate, run_detection
from .graph_engine import TransactionGraph
from . import data_gen


# ---------------------------------------------------------------------------
# Adversarial perturbation result
# ---------------------------------------------------------------------------

@dataclass
class AdversarialResult:
    """Result of running detection on a perturbed ring."""
    variation: str
    parameter: str          # e.g. "frequency=2x", "spread=3_cities"
    original_score: float   # score of the unperturbed ring
    perturbed_score: float  # score after perturbation
    score_drop: float       # original - perturbed (positive = evasion succeeded)
    detection_maintained: bool  # still above threshold after perturbation
    candidates: list[RingCandidate] = field(default_factory=list)


@dataclass
class RobustnessReport:
    """Summary of all adversarial test results."""
    results: list[AdversarialResult]
    avg_score_drop: float
    max_score_drop: float
    worst_evasion: str
    best_robustness: str
    pass_rate: float  # fraction where detection maintained


# ---------------------------------------------------------------------------
# Base ring generator (for controlled experiments)
# ---------------------------------------------------------------------------

def _generate_controlled_ring(
    rng: random.Random,
    size: int = 5,
    ring_type: str = "circular",
    seed: int = 999,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Generate a controlled ring with known members.

    Returns (users, transactions, fraud_member_ids).
    """
    users, transactions = data_gen.generate_dataset(
        n_background_users=150,
        n_background_tx=400,
        n_rings=1,
        seed=seed,
    )
    fraud_ids = {u.user_id for u in users if u.user_id.startswith("F")}
    return users, transactions, fraud_ids


def _get_ring_baseline(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    threshold: float = 55.0,
) -> tuple[list[RingCandidate], float]:
    """Get detection scores for the unperturbed ring."""
    user_index = {u.user_id: u for u in users}
    g = TransactionGraph()
    for tx in transactions:
        g.add_transaction(tx)
    shared = g.shared_attribute_graph(user_index)
    candidates = run_detection(g.snapshot(), shared, score_threshold=threshold)

    # Find the candidate with highest overlap with fraud_ids
    best_score = 0.0
    for c in candidates:
        overlap = len(set(c.members) & fraud_ids) / max(1, len(fraud_ids))
        if overlap > 0.3:
            best_score = max(best_score, c.score)

    return candidates, best_score


# ---------------------------------------------------------------------------
# Perturbation functions
# ---------------------------------------------------------------------------

def _perturb_frequency(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    multiplier: float = 2.0,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Add more transactions among ring members (frequency increase)."""
    rng = random.Random(2001)
    fraud_txs = [tx for tx in transactions if tx.sender in fraud_ids and tx.receiver in fraud_ids]
    new_txs = list(transactions)
    counter = len(transactions)

    for _ in range(int(len(fraud_txs) * (multiplier - 1))):
        base = rng.choice(fraud_txs)
        new_tx = data_gen.Transaction(
            tx_id=f"ADV{counter:06d}",
            ts=base.ts + timedelta(seconds=rng.randint(1, 30)),
            sender=base.sender,
            receiver=base.receiver,
            amount=round(base.amount * rng.uniform(0.8, 1.2), 2),
            merchant_id=None,
            sender_device=base.sender_device,
            sender_ip=base.sender_ip,
            is_fraud_ring_member=True,
            ring_id=base.ring_id,
        )
        new_txs.append(new_tx)
        counter += 1

    new_txs.sort(key=lambda t: t.ts)
    return users, new_txs, fraud_ids


def _perturb_timing(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    spread_minutes: int = 360,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Spread ring transactions over a longer window (break burst signal)."""
    rng = random.Random(2002)
    new_txs = []
    ring_start = None
    for tx in transactions:
        if tx.sender in fraud_ids or tx.receiver in fraud_ids:
            if ring_start is None:
                ring_start = tx.ts
            new_ts = ring_start + timedelta(minutes=rng.uniform(0, spread_minutes))
            new_txs.append(data_gen.Transaction(
                tx_id=tx.tx_id,
                ts=new_ts,
                sender=tx.sender,
                receiver=tx.receiver,
                amount=tx.amount,
                merchant_id=tx.merchant_id,
                sender_device=tx.sender_device,
                sender_ip=tx.sender_ip,
                is_fraud_ring_member=tx.is_fraud_ring_member,
                ring_id=tx.ring_id,
            ))
        else:
            new_txs.append(tx)
    new_txs.sort(key=lambda t: t.ts)
    return users, new_txs, fraud_ids


def _perturb_external_edges(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    n_extras: int = 5,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Add transactions between ring members and innocent users."""
    rng = random.Random(2003)
    innocent_ids = [u.user_id for u in users if u.user_id not in fraud_ids]
    fraud_list = list(fraud_ids)
    new_txs = list(transactions)
    counter = len(transactions)

    for _ in range(n_extras):
        sender = rng.choice(fraud_list)
        receiver = rng.choice(innocent_ids)
        new_txs.append(data_gen.Transaction(
            tx_id=f"ADV{counter:06d}",
            ts=rng.choice(transactions).ts + timedelta(seconds=rng.randint(1, 60)),
            sender=sender,
            receiver=receiver,
            amount=round(rng.uniform(100, 2000), 2),
            merchant_id=None,
            sender_device="D999999",
            sender_ip="10.99.99.1",
            is_fraud_ring_member=False,
            ring_id=None,
        ))
        counter += 1

    new_txs.sort(key=lambda t: t.ts)
    return users, new_txs, fraud_ids


def _perturb_innocent_members(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    n_innocent: int = 2,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Add innocent users to the ring's community (dilute fraud ratio)."""
    rng = random.Random(2004)
    innocent_pool = [u for u in users if u.user_id not in fraud_ids]
    extras = rng.sample(innocent_pool, min(n_innocent, len(innocent_pool)))
    fraud_list = list(fraud_ids)
    new_txs = list(transactions)
    counter = len(transactions)

    for extra in extras:
        # Connect innocent user to the ring
        target = rng.choice(fraud_list)
        new_txs.append(data_gen.Transaction(
            tx_id=f"ADV{counter:06d}",
            ts=rng.choice(transactions).ts + timedelta(seconds=rng.randint(1, 60)),
            sender=extra.user_id,
            receiver=target,
            amount=round(rng.uniform(100, 1500), 2),
            merchant_id=None,
            sender_device=extra.device_id,
            sender_ip=extra.ip_address,
            is_fraud_ring_member=False,
            ring_id=None,
        ))
        counter += 1

    new_txs.sort(key=lambda t: t.ts)
    return users, new_txs, fraud_ids


def _perturb_ring_size(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    target_size: int = 10,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Resize the ring by adding/removing members."""
    rng = random.Random(2005)
    current_size = len(fraud_ids)

    if target_size <= current_size:
        # Remove members (keep the first target_size)
        keep = set(list(fraud_ids)[:target_size])
        new_txs = [tx for tx in transactions
                   if not ((tx.sender in fraud_ids or tx.receiver in fraud_ids)
                           and tx.sender not in keep and tx.receiver not in keep)]
        return users, new_txs, keep

    # Add more ring members
    innocent_pool = [u for u in users if u.user_id not in fraud_ids]
    extras = rng.sample(innocent_pool, min(target_size - current_size, len(innocent_pool)))
    new_fraud = fraud_ids | {e.user_id for e in extras}
    fraud_list = list(fraud_ids)
    new_txs = list(transactions)
    counter = len(transactions)

    for extra in extras:
        target = rng.choice(fraud_list)
        new_txs.append(data_gen.Transaction(
            tx_id=f"ADV{counter:06d}",
            ts=rng.choice(transactions).ts + timedelta(seconds=rng.randint(1, 60)),
            sender=extra.user_id,
            receiver=target,
            amount=round(rng.uniform(500, 5000), 2),
            merchant_id=None,
            sender_device=extra.device_id,
            sender_ip=extra.ip_address,
            is_fraud_ring_member=True,
            ring_id=None,
        ))
        counter += 1

    new_txs.sort(key=lambda t: t.ts)
    return users, new_txs, new_fraud


def _perturb_cycle_breaking(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Remove one transaction to break the longest cycle."""
    fraud_txs = [(i, tx) for i, tx in enumerate(transactions)
                 if tx.sender in fraud_ids and tx.receiver in fraud_ids]
    if not fraud_txs:
        return users, transactions, fraud_ids

    # Remove the middle transaction (breaks the cycle)
    mid_idx = len(fraud_txs) // 2
    remove_idx = fraud_txs[mid_idx][0]
    new_txs = transactions[:remove_idx] + transactions[remove_idx + 1:]
    return users, new_txs, fraud_ids


def _perturb_amount_variation(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    variance: float = 3.0,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Make ring transaction amounts vary wildly (break amount fingerprint)."""
    rng = random.Random(2007)
    new_txs = []
    for tx in transactions:
        if tx.sender in fraud_ids and tx.receiver in fraud_ids:
            new_amount = round(tx.amount * rng.uniform(1 / variance, variance), 2)
            new_txs.append(data_gen.Transaction(
                tx_id=tx.tx_id,
                ts=tx.ts,
                sender=tx.sender,
                receiver=tx.receiver,
                amount=new_amount,
                merchant_id=tx.merchant_id,
                sender_device=tx.sender_device,
                sender_ip=tx.sender_ip,
                is_fraud_ring_member=tx.is_fraud_ring_member,
                ring_id=tx.ring_id,
            ))
        else:
            new_txs.append(tx)
    return users, new_txs, fraud_ids


def _perturb_spread(
    users: list[data_gen.User],
    transactions: list[data_gen.Transaction],
    fraud_ids: set[str],
    n_cities: int = 4,
) -> tuple[list[data_gen.User], list[data_gen.Transaction], set[str]]:
    """Spread ring members across multiple cities (break geographic clustering)."""
    rng = random.Random(2008)
    cities = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Jaipur", "Kochi"]
    chosen_cities = rng.sample(cities, min(n_cities, len(cities)))

    new_users = []
    for u in users:
        if u.user_id in fraud_ids:
            new_city = rng.choice(chosen_cities)
            new_users.append(data_gen.User(
                user_id=u.user_id,
                device_id=f"D{rng.randint(0,30000):06d}",  # different devices
                ip_address=f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.1",  # different IPs
                upi_handle=u.upi_handle,
                account_age_days=u.account_age_days,
                cohort=u.cohort,
                city=new_city,
            ))
        else:
            new_users.append(u)

    return new_users, transactions, fraud_ids


# ---------------------------------------------------------------------------
# Run all adversarial tests
# ---------------------------------------------------------------------------

# Map of perturbation name → (function, parameter_label)
PERTURBATIONS = {
    "frequency_2x": (lambda u, t, f: _perturb_frequency(u, t, f, 2.0), "frequency=2x"),
    "frequency_3x": (lambda u, t, f: _perturb_frequency(u, t, f, 3.0), "frequency=3x"),
    "timing_120min": (lambda u, t, f: _perturb_timing(u, t, f, 120), "spread=120min"),
    "timing_360min": (lambda u, t, f: _perturb_timing(u, t, f, 360), "spread=360min"),
    "external_5": (lambda u, t, f: _perturb_external_edges(u, t, f, 5), "external_edges=5"),
    "external_10": (lambda u, t, f: _perturb_external_edges(u, t, f, 10), "external_edges=10"),
    "innocent_2": (lambda u, t, f: _perturb_innocent_members(u, t, f, 2), "innocent=2"),
    "innocent_4": (lambda u, t, f: _perturb_innocent_members(u, t, f, 4), "innocent=4"),
    "ring_size_8": (lambda u, t, f: _perturb_ring_size(u, t, f, 8), "size=8"),
    "ring_size_15": (lambda u, t, f: _perturb_ring_size(u, t, f, 15), "size=15"),
    "cycle_break": (_perturb_cycle_breaking, "break_cycle"),
    "amount_var_2x": (lambda u, t, f: _perturb_amount_variation(u, t, f, 2.0), "variance=2x"),
    "amount_var_5x": (lambda u, t, f: _perturb_amount_variation(u, t, f, 5.0), "variance=5x"),
    "spread_3cities": (lambda u, t, f: _perturb_spread(u, t, f, 3), "cities=3"),
    "spread_5cities": (lambda u, t, f: _perturb_spread(u, t, f, 5), "cities=5"),
}


def run_adversarial_tests(
    seed: int = 42,
    threshold: float = 55.0,
    variations: list[str] | None = None,
) -> RobustnessReport:
    """Run all (or selected) adversarial perturbation tests.

    For each variation:
    1. Generate a baseline ring
    2. Apply the perturbation
    3. Run detection on the perturbed data
    4. Compare scores

    Returns a RobustnessReport summarizing how robust the detector is.
    """
    users, transactions, fraud_ids = _generate_controlled_ring(
        rng=random.Random(seed), seed=seed,
    )
    _, baseline_score = _get_ring_baseline(users, transactions, fraud_ids, threshold)

    active = variations or list(PERTURBATIONS.keys())
    results: list[AdversarialResult] = []

    for var_name in active:
        if var_name not in PERTURBATIONS:
            continue
        perturb_fn, param_label = PERTURBATIONS[var_name]
        perturbed_users, perturbed_txs, perturbed_fraud = perturb_fn(
            list(users), list(transactions), set(fraud_ids),
        )

        user_index = {u.user_id: u for u in perturbed_users}
        g = TransactionGraph()
        for tx in perturbed_txs:
            g.add_transaction(tx)
        shared = g.shared_attribute_graph(user_index)
        candidates = run_detection(g.snapshot(), shared, score_threshold=threshold)

        # Find best score for the perturbed ring
        best_score = 0.0
        for c in candidates:
            overlap = len(set(c.members) & perturbed_fraud) / max(1, len(perturbed_fraud))
            if overlap > 0.3:
                best_score = max(best_score, c.score)

        results.append(AdversarialResult(
            variation=var_name,
            parameter=param_label,
            original_score=baseline_score,
            perturbed_score=best_score,
            score_drop=round(baseline_score - best_score, 1),
            detection_maintained=best_score >= threshold,
            candidates=candidates,
        ))

    # Summary statistics
    drops = [r.score_drop for r in results]
    avg_drop = sum(drops) / len(drops) if drops else 0.0
    max_drop = max(drops) if drops else 0.0
    worst = max(results, key=lambda r: r.score_drop) if results else None
    best = min(results, key=lambda r: r.score_drop) if results else None
    pass_rate = sum(1 for r in results if r.detection_maintained) / len(results) if results else 0.0

    return RobustnessReport(
        results=results,
        avg_score_drop=round(avg_drop, 1),
        max_score_drop=round(max_drop, 1),
        worst_evasion=worst.variation if worst else "none",
        best_robustness=best.variation if best else "none",
        pass_rate=round(pass_rate, 3),
    )
