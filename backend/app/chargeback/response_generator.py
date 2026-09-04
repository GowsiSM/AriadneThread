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

# Reason codes where the merchant should typically contest (fraud claims).
CONTEST_REASONS = {"FRAUD", "FRAUD_ACCOUNT_TAKEOVER"}
# Reason codes where the merchant should typically accept (service issues).
ACCEPT_REASONS = {"NOT_RECEIVED", "NOT_AS_DESCRIBED", "DUPLICATE", "CANCELLED",
                  "CREDIT_NOT_PROCESSED", "RECURRING_CANCELLED"}


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
        """Decide whether to accept, contest, or request more info."""
        reason = case.get("reason_code", "")

        # Strong evidence + fraud reason -> contest.
        if reason in CONTEST_REASONS and strength >= 0.5:
            return "CONTEST"
        # Fraud reason but weak evidence -> request more info.
        if reason in CONTEST_REASONS:
            return "REQUEST_MORE_INFO"
        # Service reasons with strong evidence -> accept.
        if reason in ACCEPT_REASONS and strength >= 0.5:
            return "ACCEPT"
        # Service reasons with weak evidence -> request more info.
        if reason in ACCEPT_REASONS:
            return "REQUEST_MORE_INFO"
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
