"""
Fairness / segmented false-positive audit.

Most fraud detectors stop at an aggregate precision/recall number. This
module asks the harder question the track's "bar" explicitly requires --
honest false-positive *cost* -- broken down by customer cohort, plus a
per-ring "blast radius": what happens to legitimate users if this specific
flagged ring were auto-blocked right now.

Ground-truth labels are used here only for offline evaluation against the
synthetic dataset. In a real deployment this module would use confirmed
fraud outcomes (chargebacks, manual review verdicts) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .detection import RingCandidate


@dataclass
class CohortFPStat:
    cohort: str
    total_users: int
    flagged_users: int
    false_positives: int
    fp_rate: float
    estimated_cost_inr: float


@dataclass
class BlastRadius:
    ring_id: str
    total_members: int
    likely_innocent: int
    innocent_ratio: float
    txn_volume_last_window: float
    value_at_risk_inr: float
    dominant_cohorts: list[str]
    recommendation: str


def compute_cohort_fp_stats(
    candidates: list[RingCandidate],
    user_index: dict,
    score_threshold: float,
    avg_txn_value_by_user: dict[str, float],
) -> list[CohortFPStat]:
    flagged_users: set[str] = set()
    for c in candidates:
        if c.score >= score_threshold:
            flagged_users.update(c.members)

    cohorts: dict[str, dict] = {}
    for uid, u in user_index.items():
        cohorts.setdefault(u.cohort, {"total": 0, "flagged": 0, "fp": 0})
        cohorts[u.cohort]["total"] += 1
        if uid in flagged_users:
            cohorts[u.cohort]["flagged"] += 1
            # Ground truth: any uid starting with "F" is a planted ring member.
            if not uid.startswith("F"):
                cohorts[u.cohort]["fp"] += 1

    out: list[CohortFPStat] = []
    for cohort, stats_ in cohorts.items():
        total = stats_["total"]
        fp = stats_["fp"]
        fp_rate = fp / total if total else 0.0
        avg_value = avg_txn_value_by_user.get(cohort, 1500.0)
        # Estimated cost = blocked legitimate transaction value + a fixed
        # support-ticket handling cost proxy per false positive.
        est_cost = fp * (avg_value * 3 + 150)
        out.append(
            CohortFPStat(
                cohort=cohort,
                total_users=total,
                flagged_users=stats_["flagged"],
                false_positives=fp,
                fp_rate=round(fp_rate, 4),
                estimated_cost_inr=round(est_cost, 2),
            )
        )
    out.sort(key=lambda c: c.estimated_cost_inr, reverse=True)
    return out


def compute_blast_radius(
    candidate: RingCandidate,
    user_index: dict,
    tx_value_by_member: dict[str, float],
) -> BlastRadius:
    members = candidate.members
    innocent = [m for m in members if not m.startswith("F")]
    innocent_ratio = len(innocent) / len(members) if members else 0.0
    volume = sum(tx_value_by_member.get(m, 0.0) for m in members)

    cohort_counts: dict[str, int] = {}
    for m in members:
        u = user_index.get(m)
        if u:
            cohort_counts[u.cohort] = cohort_counts.get(u.cohort, 0) + 1
    dominant = sorted(cohort_counts, key=cohort_counts.get, reverse=True)[:2]

    if candidate.score >= 80 and innocent_ratio < 0.15:
        rec = "High confidence, low collateral -- safe for automated action within policy caps."
    elif candidate.score >= 55 and innocent_ratio < 0.4:
        rec = "Moderate confidence with some collateral risk -- recommend manual review before blocking."
    else:
        rec = "High collateral risk relative to confidence -- do not auto-block; investigate manually."

    return BlastRadius(
        ring_id=candidate.ring_id,
        total_members=len(members),
        likely_innocent=len(innocent),
        innocent_ratio=round(innocent_ratio, 3),
        txn_volume_last_window=round(volume, 2),
        value_at_risk_inr=round(volume, 2),
        dominant_cohorts=dominant,
        recommendation=rec,
    )


def precision_recall(
    candidates: list[RingCandidate],
    user_index: dict,
    score_threshold: float,
) -> dict:
    flagged_users: set[str] = set()
    for c in candidates:
        if c.score >= score_threshold:
            flagged_users.update(c.members)

    ground_truth_fraud = {uid for uid in user_index if uid.startswith("F")}
    tp = len(flagged_users & ground_truth_fraud)
    fp = len(flagged_users - ground_truth_fraud)
    fn = len(ground_truth_fraud - flagged_users)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # ring-level recall: fraction of true ring_ids that have >=50% of their
    # members captured by some single flagged candidate.
    return {
        "true_positive_users": tp,
        "false_positive_users": fp,
        "false_negative_users": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "threshold": score_threshold,
    }
