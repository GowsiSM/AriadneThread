"""
Deterministic synthetic AML/fraud dataset generator.

This is the project's primary dataset generator. It produces a fully synthetic,
seeded, labeled stream of transactions that mimics a payments network and embeds
12+ distinct fraud typologies with complete ground-truth metadata.

Design goals (from the research phase):
  * Transparent and deterministic -- same seed => same dataset.
  * Ground truth is kept SEPARATE from detector features to avoid label leakage.
  * Temporal realism -- fraud patterns are spread over time (baseline activity,
    slow fraud, sudden bursts, coordinated windows, multi-stage layering,
    delayed transfers, rapid pass-through), not all simultaneous.
  * Each fraud scenario carries a structured ground-truth record:
        {
          "scenario_id": "RING-001",
          "typology": "circular",
          "fraud_users": [...],
          "start_time": "...",
          "end_time": "...",
          "expected_detection": true
        }

No real data of any kind is used or referenced.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Iterator

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

COHORTS = [
    "new_user",
    "low_volume",
    "shared_campus_ip",
    "shared_office_ip",
    "high_value",
    "established",
]

CITIES = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Jaipur", "Kochi"]

CURRENCIES = ["INR"]

# Fraud typologies the generator can produce.
TYPOLOGIES = [
    "circular",
    "fan_in",
    "fan_out",
    "smurfing",
    "layering",
    "funnel",
    "mule_chain",
    "burst",
    "shared_device",
    "shared_ip",
    "pass_through",
    "multi_hop",
]

# Roles a fraud user can play within a ring.
ROLES = [
    "originator",
    "mule",
    "intermediary",
    "collector",
    "funnel",
    "beneficiary",
]


@dataclass
class User:
    user_id: str
    device_id: str
    ip_address: str
    upi_handle: str
    account_age_days: int
    cohort: str
    city: str
    account_type: str = "personal"
    region: str = "IN"
    risk_profile: str = "normal"
    transaction_volume: float = 0.0
    device_count: int = 1
    ip_count: int = 1


@dataclass
class Transaction:
    tx_id: str
    ts: datetime
    sender: str
    receiver: str
    amount: float
    currency: str = "INR"
    merchant_id: str | None = None
    sender_device: str = ""
    sender_ip: str = ""
    transaction_type: str = "p2p"
    # Ground truth (used ONLY for evaluation, never as detector input).
    is_fraud_ring_member: bool = False
    ring_id: str | None = None
    typology: str | None = None
    role: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class FraudScenario:
    """Ground-truth metadata for one embedded fraud ring."""
    scenario_id: str
    typology: str
    fraud_users: list[str]
    start_time: datetime
    end_time: datetime
    expected_detection: bool = True
    roles: dict[str, str] = field(default_factory=dict)  # user_id -> role

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start_time"] = self.start_time.isoformat()
        d["end_time"] = self.end_time.isoformat()
        return d


@dataclass
class Dataset:
    users: list[User]
    transactions: list[Transaction]
    scenarios: list[FraudScenario]
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "users": [asdict(u) for u in self.users],
            "transactions": [t.to_dict() for t in self.transactions],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(rng: random.Random, idx: int, cohort: str | None = None,
               user_id: str | None = None) -> User:
    cohort = cohort or rng.choice(COHORTS)
    age = {
        "new_user": rng.randint(0, 6),
        "low_volume": rng.randint(10, 400),
        "shared_campus_ip": rng.randint(0, 120),
        "shared_office_ip": rng.randint(30, 800),
        "high_value": rng.randint(200, 1500),
        "established": rng.randint(200, 1500),
    }[cohort]
    return User(
        user_id=user_id or f"U{idx:05d}",
        device_id=f"D{rng.randint(0, 30000):06d}",
        ip_address=f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        upi_handle=f"user{idx}@{rng.choice(['okhdfc', 'okaxis', 'oksbi', 'okicici'])}",
        account_age_days=age,
        cohort=cohort,
        city=rng.choice(CITIES),
    )


def _make_fraud_user(rng: random.Random, ring_idx: int, j: int,
                     shared_device: str, shared_ip_pool: list[str]) -> User:
    """A fraud-ring member. Skews toward new accounts sharing a device/IP pool,
    but mixes in a couple of older accounts so detection isn't trivial."""
    age = rng.randint(0, 4) if j < 3 else rng.randint(60, 200)
    return User(
        user_id=f"F{ring_idx:02d}{j:02d}",
        device_id=shared_device if rng.random() < 0.7 else f"D{rng.randint(0, 30000):06d}",
        ip_address=rng.choice(shared_ip_pool),
        upi_handle=f"ring{ring_idx}{j}@okhdfc",
        account_age_days=age,
        cohort="new_user" if age < 7 else "low_volume",
        city=rng.choice(CITIES),
    )


def _tx(tx_id: str, ts: datetime, sender: str, receiver: str, amount: float,
        sender_device: str, sender_ip: str, *, merchant_id: str | None = None,
        is_fraud: bool = False, ring_id: str | None = None,
        typology: str | None = None, role: str | None = None,
        transaction_type: str = "p2p") -> Transaction:
    return Transaction(
        tx_id=tx_id,
        ts=ts,
        sender=sender,
        receiver=receiver,
        amount=round(amount, 2),
        merchant_id=merchant_id,
        sender_device=sender_device,
        sender_ip=sender_ip,
        transaction_type=transaction_type,
        is_fraud_ring_member=is_fraud,
        ring_id=ring_id,
        typology=typology,
        role=role,
    )


# ---------------------------------------------------------------------------
# Typology generators
# ---------------------------------------------------------------------------

def _gen_circular(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                  ring_start, transactions):
    """A -> B -> C -> ... -> A within a short window, similar amounts."""
    amount = round(rng.uniform(4000, 9000), 2)
    for k in range(len(ring_users)):
        sender = ring_users[k]
        receiver = ring_users[(k + 1) % len(ring_users)]
        ts = ring_start + timedelta(minutes=k * rng.uniform(1, 4))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            amount * rng.uniform(0.9, 1.05), sender.device_id, sender.ip_address,
            is_fraud=True, ring_id=ring_id, typology="circular",
            role="intermediary",
        ))
        tx_counter += 1
    return tx_counter


def _gen_fan_in(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                ring_start, transactions):
    """Many sources -> single collector (money converges on one account)."""
    collector = ring_users[0]
    for k, source in enumerate(ring_users[1:]):
        ts = ring_start + timedelta(minutes=k * rng.uniform(1, 5))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, source.user_id, collector.user_id,
            rng.uniform(2000, 9500), source.device_id, source.ip_address,
            is_fraud=True, ring_id=ring_id, typology="fan_in",
            role="mule" if k % 2 else "intermediary",
        ))
        tx_counter += 1
    return tx_counter


def _gen_fan_out(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                 ring_start, transactions):
    """Single source fans out sub-threshold amounts to many mules."""
    source = ring_users[0]
    for k, receiver in enumerate(ring_users[1:]):
        ts = ring_start + timedelta(minutes=k * rng.uniform(0.5, 2))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, source.user_id, receiver.user_id,
            rng.uniform(2000, 9500), source.device_id, source.ip_address,
            is_fraud=True, ring_id=ring_id, typology="fan_out",
            role="mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_smurfing(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                  ring_start, transactions):
    """A hub receives many small sub-threshold transfers from many sources,
    then consolidates -- classic structuring."""
    hub = ring_users[0]
    # Many small deposits into the hub from external-looking sources.
    for k in range(len(ring_users) * 2):
        source = ring_users[(k % (len(ring_users) - 1)) + 1]
        ts = ring_start + timedelta(minutes=k * rng.uniform(0.3, 1.5))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, source.user_id, hub.user_id,
            rng.uniform(500, 4500), source.device_id, source.ip_address,
            is_fraud=True, ring_id=ring_id, typology="smurfing",
            role="mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_layering(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                  ring_start, transactions):
    """A -> B -> C -> D linear chain with similar amounts, hourly spacing."""
    amount = round(rng.uniform(5000, 20000), 2)
    for k in range(len(ring_users) - 1):
        sender = ring_users[k]
        receiver = ring_users[k + 1]
        ts = ring_start + timedelta(hours=k * rng.uniform(1, 3))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            amount * rng.uniform(0.9, 1.0), sender.device_id, sender.ip_address,
            is_fraud=True, ring_id=ring_id, typology="layering",
            role="intermediary" if 0 < k < len(ring_users) - 2 else "mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_funnel(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                ring_start, transactions):
    """Many sources -> single funnel account -> single beneficiary."""
    funnel = ring_users[0]
    beneficiary = ring_users[1]
    for k, source in enumerate(ring_users[2:]):
        ts = ring_start + timedelta(minutes=k * rng.uniform(1, 4))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, source.user_id, funnel.user_id,
            rng.uniform(3000, 9000), source.device_id, source.ip_address,
            is_fraud=True, ring_id=ring_id, typology="funnel",
            role="mule",
        ))
        tx_counter += 1
    # Funnel consolidates to beneficiary.
    ts = ring_start + timedelta(minutes=len(ring_users) * 4)
    transactions.append(_tx(
        f"TX{tx_counter:06d}", ts, funnel.user_id, beneficiary.user_id,
        rng.uniform(20000, 60000), funnel.device_id, funnel.ip_address,
        is_fraud=True, ring_id=ring_id, typology="funnel",
        role="funnel",
    ))
    tx_counter += 1
    return tx_counter


def _gen_mule_chain(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                    ring_start, transactions):
    """A chain of mule accounts passing money forward over days."""
    amount = round(rng.uniform(8000, 30000), 2)
    for k in range(len(ring_users) - 1):
        sender = ring_users[k]
        receiver = ring_users[k + 1]
        ts = ring_start + timedelta(days=k * rng.uniform(0.5, 1.5))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            amount * rng.uniform(0.85, 1.0), sender.device_id, sender.ip_address,
            is_fraud=True, ring_id=ring_id, typology="mule_chain",
            role="mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_burst(rng, users, tx_counter, ring_idx, ring_id, ring_users,
               ring_start, transactions):
    """Large inflow to a hub followed by rapid fan-out to many mules within
    a short window -- the classic mule-network signature."""
    hub = ring_users[0]
    big_amount = round(rng.uniform(40000, 90000), 2)
    transactions.append(_tx(
        f"TX{tx_counter:06d}", ring_start, f"U{rng.randint(0, 200):05d}",
        hub.user_id, big_amount, hub.device_id, hub.ip_address,
        is_fraud=True, ring_id=ring_id, typology="burst", role="originator",
    ))
    tx_counter += 1
    per_mule = round(big_amount / (len(ring_users) - 1), 2)
    for k, mule in enumerate(ring_users[1:]):
        ts = ring_start + timedelta(minutes=rng.uniform(1, 25))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, hub.user_id, mule.user_id,
            per_mule * rng.uniform(0.85, 1.0), hub.device_id, hub.ip_address,
            is_fraud=True, ring_id=ring_id, typology="burst", role="mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_shared_device(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                       ring_start, transactions):
    """Coordinated accounts all using the SAME device, transacting with each
    other and a common beneficiary -- no direct cycle needed."""
    shared_device = ring_users[0].device_id
    beneficiary = ring_users[0]
    for k, member in enumerate(ring_users[1:]):
        ts = ring_start + timedelta(minutes=k * rng.uniform(2, 8))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, member.user_id, beneficiary.user_id,
            rng.uniform(2000, 8000), shared_device, member.ip_address,
            is_fraud=True, ring_id=ring_id, typology="shared_device",
            role="mule",
        ))
        tx_counter += 1
    return tx_counter


def _gen_shared_ip(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                   ring_start, transactions):
    """Coordinated accounts all using the SAME IP, transacting with each other."""
    shared_ip = ring_users[0].ip_address
    for k in range(len(ring_users) - 1):
        sender = ring_users[k]
        receiver = ring_users[k + 1]
        ts = ring_start + timedelta(minutes=k * rng.uniform(1, 6))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            rng.uniform(1500, 7000), sender.device_id, shared_ip,
            is_fraud=True, ring_id=ring_id, typology="shared_ip",
            role="intermediary",
        ))
        tx_counter += 1
    return tx_counter


def _gen_pass_through(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                      ring_start, transactions):
    """Money passes rapidly through a chain of accounts in quick succession."""
    amount = round(rng.uniform(10000, 40000), 2)
    for k in range(len(ring_users) - 1):
        sender = ring_users[k]
        receiver = ring_users[k + 1]
        ts = ring_start + timedelta(seconds=k * rng.uniform(10, 90))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            amount * rng.uniform(0.95, 1.0), sender.device_id, sender.ip_address,
            is_fraud=True, ring_id=ring_id, typology="pass_through",
            role="intermediary",
        ))
        tx_counter += 1
    return tx_counter


def _gen_multi_hop(rng, users, tx_counter, ring_idx, ring_id, ring_users,
                   ring_start, transactions):
    """Multi-hop laundering: money moves through several intermediaries with
    delays, mixing with legitimate-looking external edges."""
    amount = round(rng.uniform(15000, 50000), 2)
    for k in range(len(ring_users) - 1):
        sender = ring_users[k]
        receiver = ring_users[k + 1]
        ts = ring_start + timedelta(hours=k * rng.uniform(2, 12))
        transactions.append(_tx(
            f"TX{tx_counter:06d}", ts, sender.user_id, receiver.user_id,
            amount * rng.uniform(0.8, 1.0), sender.device_id, sender.ip_address,
            is_fraud=True, ring_id=ring_id, typology="multi_hop",
            role="intermediary",
        ))
        tx_counter += 1
    return tx_counter


_TYPOLOGY_GENERATORS = {
    "circular": _gen_circular,
    "fan_in": _gen_fan_in,
    "fan_out": _gen_fan_out,
    "smurfing": _gen_smurfing,
    "layering": _gen_layering,
    "funnel": _gen_funnel,
    "mule_chain": _gen_mule_chain,
    "burst": _gen_burst,
    "shared_device": _gen_shared_device,
    "shared_ip": _gen_shared_ip,
    "pass_through": _gen_pass_through,
    "multi_hop": _gen_multi_hop,
}


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_dataset(
    n_background_users: int = 300,
    n_background_tx: int = 1200,
    n_rings: int = 12,
    seed: int = 42,
    typologies: list[str] | None = None,
    start: datetime | None = None,
    span_hours: int = 72,
) -> Dataset:
    """Generate a deterministic synthetic dataset with embedded fraud rings.

    Args:
        n_background_users: number of legitimate users.
        n_background_tx: number of legitimate background transactions.
        n_rings: number of fraud rings to embed.
        seed: RNG seed for reproducibility.
        typologies: optional explicit list of typologies (defaults to cycling
            through all 12).
        start: dataset start time (defaults to now - span).
        span_hours: how many hours of activity to simulate.

    Returns:
        A Dataset with users, transactions (sorted by ts), scenarios (ground
        truth), and meta.
    """
    rng = random.Random(seed)
    start = start or (datetime.utcnow() - timedelta(hours=span_hours))

    users: dict[str, User] = {}
    for i in range(n_background_users):
        u = _make_user(rng, i)
        users[u.user_id] = u

    # Shared IPs for legitimate campus/office cohorts (hard negatives).
    shared_ips = [f"10.99.{i}.1" for i in range(4)]
    for u in list(users.values()):
        if u.cohort in ("shared_campus_ip", "shared_office_ip"):
            u.ip_address = rng.choice(shared_ips)

    transactions: list[Transaction] = []
    merchants = [f"M{i:03d}" for i in range(40)]

    # --- background traffic (legitimate, noisy) ---
    for i in range(n_background_tx):
        sender = rng.choice(list(users.values()))
        receiver_id = rng.choice(list(users.keys()))
        ts = start + timedelta(seconds=rng.randint(0, span_hours * 3600))
        transactions.append(_tx(
            f"TX{i:06d}", ts, sender.user_id,
            receiver_id if rng.random() < 0.3 else rng.choice(merchants),
            rng.uniform(50, 9000), sender.device_id, sender.ip_address,
            merchant_id=None,
            transaction_type="p2p" if rng.random() < 0.7 else "merchant",
        ))

    tx_counter = n_background_tx

    if typologies is None:
        typologies = TYPOLOGIES * ((n_rings // len(TYPOLOGIES)) + 1)
        typologies = typologies[:n_rings]

    scenarios: list[FraudScenario] = []
    for r_idx, typology in enumerate(typologies[:n_rings]):
        ring_id = f"R{r_idx:02d}-{typology}"
        ring_size = rng.randint(5, 9)
        shared_device = f"D{rng.randint(30000, 32000):06d}"
        shared_ip_pool = [f"10.77.{r_idx}.{k}" for k in range(2)]
        ring_users = []
        for j in range(ring_size):
            u = _make_fraud_user(rng, r_idx, j, shared_device, shared_ip_pool)
            users[u.user_id] = u
            ring_users.append(u)

        ring_start = start + timedelta(
            hours=rng.randint(1, max(1, span_hours - 1))
        )
        gen = _TYPOLOGY_GENERATORS[typology]
        tx_counter = gen(rng, users, tx_counter, r_idx, ring_id, ring_users,
                         ring_start, transactions)

        # Build ground-truth scenario with roles.
        roles = {}
        for j, u in enumerate(ring_users):
            if j == 0:
                roles[u.user_id] = "originator"
            elif j == len(ring_users) - 1:
                roles[u.user_id] = "beneficiary"
            else:
                roles[u.user_id] = "intermediary"
        ring_txs = [t for t in transactions if t.ring_id == ring_id]
        end_time = max((t.ts for t in ring_txs), default=ring_start)
        scenarios.append(FraudScenario(
            scenario_id=ring_id,
            typology=typology,
            fraud_users=[u.user_id for u in ring_users],
            start_time=ring_start,
            end_time=end_time,
            expected_detection=True,
            roles=roles,
        ))

    transactions.sort(key=lambda t: t.ts)
    meta = {
        "dataset_version": "synthetic-aml-v1",
        "n_users": len(users),
        "n_transactions": len(transactions),
        "n_rings": len(scenarios),
        "typologies": sorted({s.typology for s in scenarios}),
        "seed": seed,
        "start": start.isoformat(),
        "end": (transactions[-1].ts if transactions else start).isoformat(),
    }
    return Dataset(
        users=list(users.values()),
        transactions=transactions,
        scenarios=scenarios,
        meta=meta,
    )


def iter_transactions(dataset: Dataset) -> Iterator[Transaction]:
    """Yield transactions in timestamp order (for streaming replay)."""
    yield from dataset.transactions
