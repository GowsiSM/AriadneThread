#!/usr/bin/env python3
"""
Generate the AriadneThread synthetic AML/fraud dataset.

Writes normalized CSV/JSON artifacts to data/processed/:
  * transactions.csv      -- the transaction stream (detector input)
  * users.csv             -- account metadata
  * ground_truth.json     -- fraud scenarios (labels, used ONLY for evaluation)
  * dataset_meta.json     -- dataset version + summary

Ground truth is written to a SEPARATE file so it is never mixed into the
detector feature pipeline (no label leakage).

Usage:
    python scripts/generate_synthetic_fraud.py [--users 300] [--tx 1200]
        [--rings 12] [--seed 42] [--out data/processed]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime

# Allow running from the repo root or from scripts/.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.synthetic import generate_dataset  # noqa: E402


def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _strip_ground_truth(tx: dict) -> dict:
    """Remove ground-truth columns from a transaction dict so labels never
    leak into the detector-facing feature pipeline."""
    tx = dict(tx)
    for key in ("is_fraud_ring_member", "ring_id", "typology", "role"):
        tx.pop(key, None)
    return tx


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic AML/fraud dataset")
    parser.add_argument("--users", type=int, default=300, help="background users")
    parser.add_argument("--tx", type=int, default=1200, help="background transactions")
    parser.add_argument("--rings", type=int, default=12, help="fraud rings to embed")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--span-hours", type=int, default=72, help="activity span")
    parser.add_argument("--out", default="data/processed", help="output directory")
    args = parser.parse_args()

    dataset = generate_dataset(
        n_background_users=args.users,
        n_background_tx=args.tx,
        n_rings=args.rings,
        seed=args.seed,
        span_hours=args.span_hours,
    )

    tx_rows = [_strip_ground_truth(t.to_dict()) for t in dataset.transactions]

    user_rows = [u.__dict__ for u in dataset.users]
    gt_rows = [s.to_dict() for s in dataset.scenarios]

    tx_fields = [
        "tx_id", "ts", "sender", "receiver", "amount", "currency",
        "merchant_id", "sender_device", "sender_ip", "transaction_type",
    ]
    user_fields = [
        "user_id", "device_id", "ip_address", "upi_handle", "account_age_days",
        "cohort", "city", "account_type", "region", "risk_profile",
        "transaction_volume", "device_count", "ip_count",
    ]

    tx_path = os.path.join(args.out, "transactions.csv")
    user_path = os.path.join(args.out, "users.csv")
    gt_path = os.path.join(args.out, "ground_truth.json")
    meta_path = os.path.join(args.out, "dataset_meta.json")

    write_csv(tx_path, tx_rows, tx_fields)
    write_csv(user_path, user_rows, user_fields)

    os.makedirs(args.out, exist_ok=True)
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt_rows, f, indent=2)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(dataset.meta, f, indent=2)

    print(f"Wrote {len(tx_rows)} transactions -> {tx_path}")
    print(f"Wrote {len(user_rows)} users -> {user_path}")
    print(f"Wrote {len(gt_rows)} fraud scenarios -> {gt_path}")
    print(f"Wrote dataset meta -> {meta_path}")
    print(f"Typologies: {dataset.meta['typologies']}")


if __name__ == "__main__":
    main()
