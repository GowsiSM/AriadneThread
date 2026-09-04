"""
ResponseGenerator: assembles collected evidence into a structured chargeback
response package.

A chargeback response is the merchant's formal reply to a cardholder dispute.
It bundles the prioritized evidence with a recommendation (accept / contest /
request more info) and a human-readable narrative so an analyst can review and
submit it to the card network.

This is a *supplementary* layer on top of the deterministic graph detector --
it never changes detection decisions, it only packages evidence for disputes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .evidence_priority import REASON_PRIORITY

# Reason codes where the merchant should typically contest (fraud claims).
CONTEST_REASONS = {"FRAUD", "FRAUD_ACCOUNT_TAKEOVER"}
# Reason codes where the merchant should typically accept (service issues).
ACCEPT_REASONS = {"NOT_RECEIVED", "NOT_AS_DESCRIBED", "DUPLICATE", "CANCELLED",
                  "CREDIT_NOT_PROCESSED", "RECURRING_CANCELLED"}

# Per-category strength weights for reason-aware scoring.
_CATEGORY_WEIGHTS = {
    "transaction": 0.20,
    "customer": 0.15,
    "device": 0.20,
    "authentication": 0.25,
    "delivery": 0.10,
    "ml_risk": 0.10,
}


class ResponseGenerator:
    """Builds a structured chargeback response package from evidence."""

    def generate_response(self, case: dict, evidence_result: dict) -> dict:
        """Generate a full response package for a chargeback case.

        Args:
            case: the chargeback case dict.
            evidence_result: the output of EvidenceEngine.collect_evidence.

        Returns:
            A dict with response_id, case_id, recommendation, narrative,
            evidence (prioritized), evidence_strength, and generated_at.
        """
        evidence = evidence_result.get("evidence", {})
        priority = evidence_result.get("priority", [])
        strength = evidence_result.get("evidence_strength", 0.0)

        recommendation = self._recommend(case, evidence, strength)
        narrative = self._build_narrative(case, evidence, recommendation)

        return {
            "response_id": f"RESP-{case.get('case_id', 'UNKNOWN')}",
            "case_id": case.get("case_id", ""),
            "recommendation": recommendation,
            "narrative": narrative,
            "evidence": priority,
            "evidence_strength": strength,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _recommend(self, case: dict, evidence: dict, strength: float) -> str:
        """Decide whether to accept, contest, or request more info.

        Uses the top 3 evidence categories from REASON_PRIORITY for the
        chargeback reason code, and checks ml_risk direction explicitly
        (low risk supports contest; high risk supports accept/investigate).
        """
        reason = case.get("reason_code", "")
        priority_cats = REASON_PRIORITY.get(reason, ["transaction", "customer", "device"])

        # Build a reason-relevant score from the top-priority categories.
        top3 = priority_cats[:3]
        reason_score = 0.0
        reason_weight = 0.0
        for cat in top3:
            cat_data = evidence.get(cat, {})
            w = _CATEGORY_WEIGHTS.get(cat, 0.1)
            if cat == "ml_risk":
                if cat_data.get("available"):
                    # Low fraud score = strong evidence FOR the merchant (supports contest).
                    # High fraud score = evidence AGAINST contesting.
                    risk = float(cat_data.get("risk_score", 0.5) or 0.5)
                    reason_score += (1.0 - risk) * w
                else:
                    reason_score += 0.5 * w  # unknown — neutral
            elif cat == "authentication":
                auth = cat_data.get("auth_strength", "unknown")
                reason_score += {"strong": 0.9, "moderate": 0.5, "weak": 0.2}.get(auth, 0.3) * w
            elif cat == "device":
                known = sum(1 for k in ("device_known", "ip_known") if cat_data.get(k))
                reason_score += [0.0, 0.4, 0.8][known] * w
            elif cat == "delivery":
                # Delivery evidence is a stub — treat as low confidence.
                reason_score += 0.05 * w
            elif cat == "transaction":
                reason_score += (0.8 if cat_data.get("transaction_id") else 0.0) * w
            elif cat == "customer":
                reason_score += (0.7 if cat_data.get("cardholder") else 0.0) * w
            else:
                reason_score += 0.3 * w
            reason_weight += w

        if reason_weight > 0:
            reason_score = reason_score / reason_weight

        # --- Decision logic ---
        if reason in CONTEST_REASONS:
            # For fraud claims: contest if reason-relevant evidence is strong
            # AND ML risk is low (transaction looks legitimate).
            ml_risk = evidence.get("ml_risk", {})
            ml_score = ml_risk.get("risk_score")
            ml_high = ml_risk.get("available") and ml_score is not None and float(ml_score) > 0.7

            if ml_high:
                # High ML fraud risk argues AGAINST contesting.
                return "REQUEST_MORE_INFO"
            if reason_score >= 0.5:
                return "CONTEST"
            return "REQUEST_MORE_INFO"

        if reason in ACCEPT_REASONS:
            # For service issues: accept if the dispute is plausible and
            # evidence doesn't strongly favor the merchant.
            if reason_score < 0.4:
                return "ACCEPT"
            if reason_score >= 0.6:
                return "REQUEST_MORE_INFO"
            return "ACCEPT"

        return "REQUEST_MORE_INFO"

    def _build_narrative(self, case: dict, evidence: dict, recommendation: str) -> str:
        """Build a short human-readable narrative for the response."""
        reason = case.get("reason_code", "UNKNOWN")
        amount = case.get("amount", 0)
        tx_id = case.get("transaction_id", "")
        merchant = case.get("merchant", "")

        auth = evidence.get("authentication", {})
        auth_strength = auth.get("auth_strength", "unknown")
        ml = evidence.get("ml_risk", {})
        ml_level = ml.get("risk_level", "unknown")

        if recommendation == "CONTEST":
            narrative = (
                f"Contesting chargeback {case.get('case_id', '')} for {amount} on "
                f"transaction {tx_id} at {merchant}. The transaction shows "
                f"{auth_strength} authentication evidence and the ML model rates "
                f"fraud risk as {ml_level}. We believe the transaction was "
                f"authorized and legitimate."
            )
        elif recommendation == "ACCEPT":
            narrative = (
                f"Accepting chargeback {case.get('case_id', '')} for {amount} on "
                f"transaction {tx_id} at {merchant}. The dispute reason ({reason}) "
                f"is a service issue and we do not have sufficient evidence to "
                f"contest it."
            )
        else:
            narrative = (
                f"Requesting more information for chargeback {case.get('case_id', '')} "
                f"for {amount} on transaction {tx_id} at {merchant}. Current "
                f"evidence strength is insufficient to make a final determination."
            )
        return narrative
