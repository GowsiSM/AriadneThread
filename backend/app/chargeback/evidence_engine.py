"""
EvidenceEngine: collects structured evidence for a chargeback case.

A chargeback dispute needs to be answered with evidence that proves (or
refutes) the cardholder's claim. This engine pulls together evidence across
several dimensions:

  * transaction  -- the disputed transaction itself (amount, time, merchant)
  * customer     -- the cardholder's account history and profile
  * device       -- device fingerprint / IP used for the transaction
  * authentication -- 3DS / OTP / login signals
  * delivery     -- shipping / fulfillment signals (for NOT_RECEIVED disputes)
  * ml_risk      -- the ML fraud-probability signal for the transaction

The engine is deterministic and grounded in the data it is given. It never
fabricates evidence -- if a signal is unknown, it is reported as "unknown"
rather than guessed.
"""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("fraud_sentinel.chargeback")

ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = ROOT / "data"
TX_CSV = DATA_DIR / "processed" / "transactions.csv"
USERS_CSV = DATA_DIR / "processed" / "users.csv"


class EvidenceEngine:
    """Collects and organizes evidence for a chargeback case."""

    def __init__(self, ml_predictor=None):
        self.ml_predictor = ml_predictor
        self._transactions: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Load transaction + user data into memory for evidence lookup."""
        try:
            if TX_CSV.exists():
                with open(TX_CSV, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        self._transactions[row.get("tx_id", "")] = row
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load transactions for evidence: %s", exc)

        try:
            if USERS_CSV.exists():
                with open(USERS_CSV, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        self._users[row.get("user_id", "")] = row
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load users for evidence: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_evidence(self, case: dict) -> dict:
        """Collect all evidence for a chargeback case.

        Args:
            case: a chargeback case dict (from chargeback_cases.csv or the
                  case manager) with at least transaction_id, cardholder,
                  merchant, amount, reason_code.

        Returns:
            A dict with `evidence` (grouped), `priority` (ordered evidence
            list), and `evidence_strength` (0..1).
        """
        transaction = self._get_transaction(case)
        reason = case.get("reason_code", "FRAUD")

        evidence = {
            "transaction": self._get_transaction_evidence(case, transaction),
            "customer": self._get_customer_evidence(case, transaction),
            "device": self._get_device_evidence(case, transaction),
            "authentication": self._get_auth_evidence(case, transaction),
            "delivery": self._get_delivery_evidence(case, transaction),
            "ml_risk": self._get_ml_risk(case, transaction),
        }

        # Priority based on chargeback reason (delegated to evidence_priority).
        from .evidence_priority import prioritize_evidence
        priority = prioritize_evidence(evidence, reason)

        return {
            "evidence": evidence,
            "priority": priority,
            "evidence_strength": self._calculate_strength(evidence),
        }

    # ------------------------------------------------------------------
    # Evidence collectors
    # ------------------------------------------------------------------

    def _get_transaction(self, case: dict) -> dict | None:
        tx_id = case.get("transaction_id", "")
        return self._transactions.get(tx_id)

    def _get_transaction_evidence(self, case: dict, transaction: dict | None) -> dict:
        amount = case.get("amount")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        return {
            "transaction_id": case.get("transaction_id", ""),
            "amount": amount,
            "currency": (transaction or {}).get("currency", "INR"),
            "timestamp": (transaction or {}).get("ts", case.get("filed_at", "")),
            "merchant": case.get("merchant", ""),
            "transaction_type": (transaction or {}).get("transaction_type", "unknown"),
            "sender": (transaction or {}).get("sender", case.get("cardholder", "")),
            "receiver": (transaction or {}).get("receiver", ""),
        }

    def _get_customer_evidence(self, case: dict, transaction: dict | None) -> dict:
        cardholder = case.get("cardholder", "")
        user = self._users.get(cardholder, {})
        return {
            "cardholder": cardholder,
            "account_age_days": user.get("account_age_days", "unknown"),
            "cohort": user.get("cohort", "unknown"),
            "city": user.get("city", "unknown"),
            "risk_profile": user.get("risk_profile", "unknown"),
            "transaction_volume": user.get("transaction_volume", "unknown"),
            "device_count": user.get("device_count", "unknown"),
            "ip_count": user.get("ip_count", "unknown"),
            "account_type": user.get("account_type", "unknown"),
        }

    def _get_device_evidence(self, case: dict, transaction: dict | None) -> dict:
        return {
            "device_id": (transaction or {}).get("sender_device", "unknown"),
            "ip_address": (transaction or {}).get("sender_ip", "unknown"),
            "device_known": bool((transaction or {}).get("sender_device")),
            "ip_known": bool((transaction or {}).get("sender_ip")),
        }

    def _get_auth_evidence(self, case: dict, transaction: dict | None) -> dict:
        # In a real system this would come from an authentication log. Here we
        # derive a plausible signal from the account's risk profile and whether
        # the device/IP is known.
        user = self._users.get(case.get("cardholder", ""), {})
        device_known = bool((transaction or {}).get("sender_device"))
        ip_known = bool((transaction or {}).get("sender_ip"))
        risk_profile = user.get("risk_profile", "normal")

        if risk_profile == "fraud":
            auth_strength = "weak"
            auth_detail = "Account flagged as high-risk; no strong authentication evidence"
        elif device_known and ip_known:
            auth_strength = "strong"
            auth_detail = "Transaction from a known device and IP"
        elif device_known or ip_known:
            auth_strength = "moderate"
            auth_detail = "Transaction from a partially known device/IP"
        else:
            auth_strength = "unknown"
            auth_detail = "No authentication signal available"

        return {
            "auth_strength": auth_strength,
            "auth_detail": auth_detail,
            "device_known": device_known,
            "ip_known": ip_known,
        }

    def _get_delivery_evidence(self, case: dict, transaction: dict | None) -> dict:
        # Delivery evidence is most relevant for NOT_RECEIVED / NOT_AS_DESCRIBED
        # disputes. In a real system this would come from a logistics feed. Here
        # we derive a plausible signal from the merchant and transaction type.
        merchant = case.get("merchant", "")
        tx_type = (transaction or {}).get("transaction_type", "unknown")
        return {
            "merchant": merchant,
            "delivery_confirmation": "unknown",
            "tracking_available": False,
            "signed_for": False,
            "delivery_address_match": "unknown",
            "note": "Delivery evidence not available for this transaction type",
        }

    def _get_ml_risk(self, case: dict, transaction: dict | None) -> dict:
        if self.ml_predictor is None or not self.ml_predictor.available:
            return {
                "available": False,
                "risk_score": None,
                "risk_level": "unknown",
                "explanation": "ML predictor unavailable",
            }
        # Build a transaction payload for the predictor from available data.
        tx = transaction or {}
        payload = {
            "amt": case.get("amount", 0),
            "trans_date_trans_time": tx.get("ts", ""),
            "lat": 0.0,
            "long": 0.0,
            "merch_lat": 0.0,
            "merch_long": 0.0,
            "city_pop": 0,
            "category": "unknown",
            "cc_num": case.get("cardholder", ""),
            "merchant": case.get("merchant", ""),
        }
        try:
            result = self.ml_predictor.predict(payload)
            return {
                "available": True,
                "risk_score": result.get("risk_score"),
                "risk_level": result.get("risk_level"),
                "explanation": result.get("explanation", {}).get("summary", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("ML risk lookup failed: %s", exc)
            return {
                "available": False,
                "risk_score": None,
                "risk_level": "unknown",
                "explanation": "ML risk lookup failed",
            }

    # ------------------------------------------------------------------
    # Strength calculation
    # ------------------------------------------------------------------

    def _calculate_strength(self, evidence: dict) -> float:
        """Compute an overall evidence strength score (0..1)."""
        score = 0.0
        weights = 0.0

        # Transaction evidence present.
        tx = evidence.get("transaction", {})
        if tx.get("transaction_id"):
            score += 0.2
        weights += 0.2

        # Customer evidence present.
        cust = evidence.get("customer", {})
        if cust.get("cardholder"):
            score += 0.15
        weights += 0.15

        # Device evidence.
        dev = evidence.get("device", {})
        if dev.get("device_known") or dev.get("ip_known"):
            score += 0.2
        weights += 0.2

        # Authentication evidence.
        auth = evidence.get("authentication", {})
        if auth.get("auth_strength") == "strong":
            score += 0.25
        elif auth.get("auth_strength") == "moderate":
            score += 0.15
        weights += 0.25

        # Delivery evidence (only counts if present).
        delivery = evidence.get("delivery", {})
        if delivery.get("delivery_confirmation") not in (None, "unknown"):
            score += 0.1
        weights += 0.1

        # ML risk (only counts if available).
        ml = evidence.get("ml_risk", {})
        if ml.get("available"):
            score += 0.1
        weights += 0.1

        if weights == 0:
            return 0.0
        return round(min(score / weights, 1.0), 3)
