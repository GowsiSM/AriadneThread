#!/usr/bin/env python3
"""
Generate synthetic chargeback cases for the Chargeback Evidence Responder.

A chargeback is a cardholder dispute against a transaction. This script builds
a deterministic set of chargeback cases that reference the synthetic
transaction stream (data/processed/transactions.csv + users.csv) and the
Sparkov-style fraud dataset (data/fraudTrain.csv) so the evidence engine has
realistic transaction/customer/device/delivery data to pull from.

Output: data/chargeback_cases.csv

Each row is one chargeback case with:
  * case_id            -- unique chargeback reference
  * transaction_id     -- the disputed transaction
  * cardholder         -- the account that filed the dispute
  * merchant           -- the merchant involved
  * amount             -- disputed amount
  * reason_code        -- chargeback reason (e.g. FRAUD, NOT_RECEIVED, ...)
  * reason_description -- human-readable reason
  * filed_at           -- when the dispute was filed
  * status             -- OPEN / UNDER_REVIEW / RESPONDED / CLOSED
  * priority           -- LOW / MEDIUM / HIGH / CRITICAL
  * is_fraud           -- ground-truth label (for evaluation only)
"""
from __future__ import annotations

import csv
import os
import random
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
TX_CSV = os.path.join(DATA_DIR, "processed", "transactions.csv")
USERS_CSV = os.path.join(DATA_DIR, "processed", "users.csv")
OUT_CSV = os.path.join(DATA_DIR, "chargeback_cases.csv")

# Chargeback reason codes (Visa/Mastercard-style) mapped to descriptions.
REASON_CODES = [
    ("FRAUD", "Cardholder claims the transaction was not authorized"),
    ("NOT_RECEIVED", "Cardholder did not receive the goods/services"),
    ("NOT_AS_DESCRIBED", "Goods/services materially different from description"),
    ("DUPLICATE", "Cardholder was charged more than once for the same purchase"),
    ("CANCELLED", "Cardholder cancelled but was still charged"),
    ("CREDIT_NOT_PROCESSED", "Merchant agreed to refund but did not process it"),
    ("RECURRING_CANCELLED", "Recurring billing continued after cancellation"),
    ("FRAUD_ACCOUNT_TAKEOVER", "Account was taken over by a fraudster"),
]

# Reason codes that are strongly tied to genuine fraud (higher base risk).
FRAUD_TIED_REASONS = {"FRAUD", "FRAUD_ACCOUNT_TAKEOVER"}


def _load_transactions() -> list[dict]:
    rows = []
    with open(TX_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def _load_users() -> dict[str, dict]:
    users = {}
    with open(USERS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            users[r["user_id"]] = r
    return users


def _pick_reason(rng: random.Random, is_fraud: bool) -> tuple[str, str]:
    if is_fraud:
        # Fraudulent transactions are more likely to be disputed as fraud.
        pool = ["FRAUD", "FRAUD", "FRAUD_ACCOUNT_TAKEOVER", "NOT_RECEIVED", "NOT_AS_DESCRIBED"]
    else:
        pool = [rc for rc, _ in REASON_CODES if rc not in FRAUD_TIED_REASONS]
    code = rng.choice(pool)
    desc = dict(REASON_CODES)[code]
    return code, desc


def main() -> None:
    rng = random.Random(42)
    transactions = _load_transactions()
    users = _load_users()

    if not transactions:
        print("No transactions found. Run the backend once to generate data/processed/* first.")
        return

    # Only consider merchant transactions (chargebacks are card purchases).
    merchant_tx = [t for t in transactions if t.get("transaction_type") == "merchant"]
    if not merchant_tx:
        merchant_tx = transactions

    # Sample a deterministic subset of transactions to dispute.
    n_cases = min(120, len(merchant_tx))
    disputed = rng.sample(merchant_tx, n_cases)

    os.makedirs(DATA_DIR, exist_ok=True)
    fields = [
        "case_id", "transaction_id", "cardholder", "merchant", "amount",
        "reason_code", "reason_description", "filed_at", "status", "priority",
        "is_fraud",
    ]

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, tx in enumerate(disputed):
            # Ground-truth fraud label: a transaction is "fraud" if either the
            # sender is a known fraud-ring member OR the amount is unusually high
            # relative to the cardholder's history (proxy for Sparkov-style fraud).
            sender = tx.get("sender", "")
            user = users.get(sender, {})
            is_fraud = user.get("risk_profile") == "fraud" or rng.random() < 0.18

            reason_code, reason_desc = _pick_reason(rng, is_fraud)

            # Priority derived from reason + amount.
            amount = float(tx.get("amount", 0) or 0)
            if is_fraud or reason_code in FRAUD_TIED_REASONS:
                priority = "CRITICAL" if amount > 5000 else "HIGH"
            elif amount > 10000:
                priority = "HIGH"
            elif amount > 2000:
                priority = "MEDIUM"
            else:
                priority = "LOW"

            filed_at = datetime.utcnow() - timedelta(days=rng.randint(0, 30))
            writer.writerow({
                "case_id": f"CB-{i:04d}",
                "transaction_id": tx.get("tx_id", ""),
                "cardholder": sender,
                "merchant": tx.get("receiver", ""),
                "amount": f"{amount:.2f}",
                "reason_code": reason_code,
                "reason_description": reason_desc,
                "filed_at": filed_at.isoformat(),
                "status": "OPEN",
                "priority": priority,
                "is_fraud": int(is_fraud),
            })

    print(f"Wrote {n_cases} chargeback cases -> {OUT_CSV}")


if __name__ == "__main__":
    main()
