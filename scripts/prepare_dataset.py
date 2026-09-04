#!/usr/bin/env python3
"""
Normalize an external transaction dataset into AriadneThread's schema.

This is primarily used to normalize the IBM AMLworld HI-Small dataset (if the
user downloaded it via scripts/download_dataset.py) into our standard
transactions.csv / users.csv / ground_truth.json layout.

It is fully optional -- the project's primary dataset comes from our own
deterministic generator. This script exists so that, when a user has the IBM
data locally, it can be compared against our generator on the same schema.

Usage:
    python scripts/prepare_dataset.py --src data/raw/ibm_amlworld --out data/processed/ibm
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta


def _parse_ts(raw: str) -> str:
    """IBM AMLworld timestamps are like '2017/1/1 0:00'. Normalize to ISO."""
    try:
        dt = datetime.strptime(raw.strip(), "%Y/%m/%d %H:%M")
    except ValueError:
        try:
            dt = datetime.fromisoformat(raw.strip())
        except ValueError:
            dt = datetime.utcnow()
    return dt.isoformat()


def prepare_ibm(src: str, out: str) -> None:
    tx_path = os.path.join(src, "HI-Small_Trans.csv")
    if not os.path.exists(tx_path):
        print(f"Source file not found: {tx_path}")
        print("Run scripts/download_dataset.py first, or use our own generator.")
        sys.exit(1)

    os.makedirs(out, exist_ok=True)
    tx_out = os.path.join(out, "transactions.csv")
    gt_out = os.path.join(out, "ground_truth.json")

    tx_fields = [
        "tx_id", "ts", "sender", "receiver", "amount", "currency",
        "merchant_id", "sender_device", "sender_ip", "transaction_type",
    ]
    scenarios = {}
    n = 0
    with open(tx_path, newline="", encoding="utf-8") as fin, \
         open(tx_out, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=tx_fields)
        writer.writeheader()
        for row in reader:
            is_laundering = row.get("is_laundering", "0") == "1"
            # Composite node id: {bank}_{account} (account numbers repeat across banks).
            sender = f"{row.get('from_bank', '')}_{row.get('from_acct', '')}"
            receiver = f"{row.get('to_bank', '')}_{row.get('to_acct', '')}"
            writer.writerow({
                "tx_id": f"IBM{n:08d}",
                "ts": _parse_ts(row.get("timestamp", "")),
                "sender": sender,
                "receiver": receiver,
                "amount": row.get("amount_received", "0"),
                "currency": row.get("recv_currency", "USD"),
                "merchant_id": None,
                "sender_device": "",
                "sender_ip": "",
                "transaction_type": "p2p",
            })
            if is_laundering:
                scenarios.setdefault(sender, {"fraud_users": [], "typology": "unknown"})
                scenarios[sender]["fraud_users"].append(sender)
            n += 1

    with open(gt_out, "w", encoding="utf-8") as f:
        json.dump(list(scenarios.values()), f, indent=2)

    print(f"Normalized {n} transactions -> {tx_out}")
    print(f"Wrote {len(scenarios)} laundering scenarios -> {gt_out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize external dataset into our schema")
    parser.add_argument("--src", default="data/raw/ibm_amlworld", help="source directory")
    parser.add_argument("--out", default="data/processed/ibm", help="output directory")
    args = parser.parse_args()
    prepare_ibm(args.src, args.out)


if __name__ == "__main__":
    main()
