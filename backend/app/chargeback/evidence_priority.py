"""
EvidencePriority: ranks collected evidence by how relevant it is to a given
chargeback reason code.

Different chargeback reasons need different evidence. For example:
  * FRAUD / FRAUD_ACCOUNT_TAKEOVER  -> authentication + device + ML risk matter most
  * NOT_RECEIVED / NOT_AS_DESCRIBED -> delivery + transaction evidence matter most
  * DUPLICATE / CANCELLED           -> transaction history matters most

This module returns an ordered list of evidence items (highest priority first)
so the response generator can present the strongest, most relevant evidence
first.
"""
from __future__ import annotations

# Map each chargeback reason to the evidence categories that matter most,
# in priority order (first = most important).
REASON_PRIORITY = {
    "FRAUD": ["authentication", "device", "ml_risk", "transaction", "customer", "delivery"],
    "FRAUD_ACCOUNT_TAKEOVER": ["authentication", "device", "ml_risk", "customer", "transaction", "delivery"],
    "NOT_RECEIVED": ["delivery", "transaction", "customer", "device", "authentication", "ml_risk"],
    "NOT_AS_DESCRIBED": ["delivery", "transaction", "customer", "device", "authentication", "ml_risk"],
    "DUPLICATE": ["transaction", "customer", "device", "authentication", "delivery", "ml_risk"],
    "CANCELLED": ["transaction", "customer", "device", "authentication", "delivery", "ml_risk"],
    "CREDIT_NOT_PROCESSED": ["transaction", "customer", "device", "authentication", "delivery", "ml_risk"],
    "RECURRING_CANCELLED": ["transaction", "customer", "device", "authentication", "delivery", "ml_risk"],
}

# Default ordering for unknown reasons.
DEFAULT_PRIORITY = ["transaction", "customer", "device", "authentication", "delivery", "ml_risk"]

# Human-readable labels for each evidence category.
CATEGORY_LABELS = {
    "transaction": "Transaction Record",
    "customer": "Customer Account History",
    "device": "Device & IP Evidence",
    "authentication": "Authentication Evidence",
    "delivery": "Delivery / Fulfillment Evidence",
    "ml_risk": "ML Fraud Risk Signal",
}


def prioritize_evidence(evidence: dict, reason_code: str) -> list[dict]:
    """Return an ordered list of evidence items, highest priority first.

    Args:
        evidence: the grouped evidence dict from EvidenceEngine.collect_evidence.
        reason_code: the chargeback reason code (e.g. "FRAUD").

    Returns:
        A list of dicts: [{"category": ..., "label": ..., "data": ...}, ...]
        ordered by relevance to the reason code.
    """
    order = REASON_PRIORITY.get(reason_code, DEFAULT_PRIORITY)

    prioritized = []
    for category in order:
        data = evidence.get(category)
        if data is None:
            continue
        prioritized.append({
            "category": category,
            "label": CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
            "data": data,
        })
    return prioritized
