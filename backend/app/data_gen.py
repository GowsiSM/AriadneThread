"""
Synthetic transaction generator.

Produces a fully synthetic, labeled stream of transactions that mimics a
payments network. A small number of "fraud rings" are deliberately embedded
using three distinct topologies (circular, fan-out/structuring, burst/mule)
so the detection engine and its precision/recall metrics have known ground
truth to be evaluated against. Everything else is background noise designed
to *look* superficially similar to fraud patterns (shared campus/office IPs,
bursts of legitimate payday transfers) so the detector is forced to
discriminate rather than pattern-match on trivial signals.

No real data of any kind is used or referenced.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Iterator

COHORTS = [
    "new_user",
    "low_volume",
    "shared_campus_ip",
    "shared_office_ip",
    "high_value",
    "established",
]

CITIES = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Jaipur", "Kochi"]


@dataclass
class User:
    user_id: str
    device_id: str
    ip_address: str
    upi_handle: str
    account_age_days: int
    cohort: str
    city: str


@dataclass
class Transaction:
    tx_id: str
    ts: datetime
    sender: str
    receiver: str
    amount: float
    merchant_id: str | None
    sender_device: str
    sender_ip: str
    is_fraud_ring_member: bool
    ring_id: str | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


def _make_user(rng: random.Random, idx: int, cohort: str | None = None) -> User:
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
        user_id=f"U{idx:05d}",
        device_id=f"D{rng.randint(0, 30000):06d}",
        ip_address=f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
        upi_handle=f"user{idx}@{rng.choice(['okhdfc','okaxis','oksbi','okicici'])}",
        account_age_days=age,
        cohort=cohort,
        city=rng.choice(CITIES),
    )


def generate_dataset(
    n_background_users: int = 300,
    n_background_tx: int = 1200,
    n_rings: int = 3,
    seed: int = 42,
) -> tuple[list[User], list[Transaction]]:
    """Generate a deterministic (seeded) synthetic dataset.

    Returns (users, transactions) sorted by timestamp ascending. Transactions
    carry ground-truth `is_fraud_ring_member` / `ring_id` labels used ONLY
    for offline evaluation (precision/recall) -- the detector never sees
    these labels.
    """
    rng = random.Random(seed)
    start = datetime.utcnow() - timedelta(hours=2)

    users: dict[str, User] = {}
    for i in range(n_background_users):
        u = _make_user(rng, i)
        users[u.user_id] = u

    # A handful of shared IPs (campus/office) that legitimately have many
    # distinct users -- this is the "hard negative" that a naive shared-IP
    # heuristic would false-positive on.
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
        ts = start + timedelta(seconds=rng.randint(0, 7100))
        transactions.append(
            Transaction(
                tx_id=f"TX{i:06d}",
                ts=ts,
                sender=sender.user_id,
                receiver=receiver_id if rng.random() < 0.3 else rng.choice(merchants),
                amount=round(rng.uniform(50, 9000), 2),
                merchant_id=None,
                sender_device=sender.device_id,
                sender_ip=sender.ip_address,
                is_fraud_ring_member=False,
                ring_id=None,
            )
        )

    tx_counter = n_background_tx
    ring_types = ["circular", "fanout", "burst"][:n_rings] if n_rings <= 3 else (
        ["circular", "fanout", "burst"] * ((n_rings // 3) + 1)
    )[:n_rings]

    for r_idx, ring_type in enumerate(ring_types):
        ring_id = f"R{r_idx:02d}-{ring_type}"
        ring_size = rng.randint(5, 9)
        # Fraud rings skew toward new accounts sharing one device/IP pool --
        # a genuine, common fraud signature -- but we mix in a couple of
        # older accounts to avoid making detection trivially easy.
        ring_users = []
        shared_device = f"D{rng.randint(30000, 32000):06d}"
        shared_ip_pool = [f"10.77.{r_idx}.{k}" for k in range(2)]
        for j in range(ring_size):
            age = rng.randint(0, 4) if j < ring_size - 2 else rng.randint(60, 200)
            u = User(
                user_id=f"F{r_idx:02d}{j:02d}",
                device_id=shared_device if rng.random() < 0.7 else f"D{rng.randint(0,30000):06d}",
                ip_address=rng.choice(shared_ip_pool),
                upi_handle=f"ring{r_idx}{j}@okhdfc",
                account_age_days=age,
                cohort="new_user" if age < 7 else "low_volume",
                city=rng.choice(CITIES),
            )
            users[u.user_id] = u
            ring_users.append(u)

        ring_start = start + timedelta(minutes=rng.randint(20, 100))

        if ring_type == "circular":
            # A -> B -> C -> ... -> A within a short window and similar amounts
            amount = round(rng.uniform(4000, 9000), 2)
            for k in range(len(ring_users)):
                sender = ring_users[k]
                receiver = ring_users[(k + 1) % len(ring_users)]
                ts = ring_start + timedelta(minutes=k * rng.uniform(1, 4))
                transactions.append(
                    Transaction(
                        tx_id=f"TX{tx_counter:06d}",
                        ts=ts,
                        sender=sender.user_id,
                        receiver=receiver.user_id,
                        amount=amount * rng.uniform(0.9, 1.05),
                        merchant_id=None,
                        sender_device=sender.device_id,
                        sender_ip=sender.ip_address,
                        is_fraud_ring_member=True,
                        ring_id=ring_id,
                    )
                )
                tx_counter += 1

        elif ring_type == "fanout":
            # Single collector fans out sub-threshold amounts to many mules
            source = ring_users[0]
            for k, receiver in enumerate(ring_users[1:]):
                ts = ring_start + timedelta(minutes=k * rng.uniform(0.5, 2))
                transactions.append(
                    Transaction(
                        tx_id=f"TX{tx_counter:06d}",
                        ts=ts,
                        sender=source.user_id,
                        receiver=receiver.user_id,
                        amount=round(rng.uniform(2000, 9500), 2),  # just under a 10k threshold
                        merchant_id=None,
                        sender_device=source.device_id,
                        sender_ip=source.ip_address,
                        is_fraud_ring_member=True,
                        ring_id=ring_id,
                    )
                )
                tx_counter += 1

        else:  # burst / mule network
            hub = ring_users[0]
            big_amount = round(rng.uniform(40000, 90000), 2)
            transactions.append(
                Transaction(
                    tx_id=f"TX{tx_counter:06d}",
                    ts=ring_start,
                    sender=f"U{rng.randint(0, n_background_users-1):05d}",
                    receiver=hub.user_id,
                    amount=big_amount,
                    merchant_id=None,
                    sender_device=hub.device_id,
                    sender_ip=hub.ip_address,
                    is_fraud_ring_member=True,
                    ring_id=ring_id,
                )
            )
            tx_counter += 1
            per_mule = round(big_amount / (len(ring_users) - 1), 2)
            for k, mule in enumerate(ring_users[1:]):
                ts = ring_start + timedelta(minutes=rng.uniform(1, 25))
                transactions.append(
                    Transaction(
                        tx_id=f"TX{tx_counter:06d}",
                        ts=ts,
                        sender=hub.user_id,
                        receiver=mule.user_id,
                        amount=per_mule * rng.uniform(0.85, 1.0),
                        merchant_id=None,
                        sender_device=hub.device_id,
                        sender_ip=hub.ip_address,
                        is_fraud_ring_member=True,
                        ring_id=ring_id,
                    )
                )
                tx_counter += 1

    transactions.sort(key=lambda t: t.ts)
    return list(users.values()), transactions


def stream(transactions: list[Transaction]) -> Iterator[Transaction]:
    for t in transactions:
        yield t
