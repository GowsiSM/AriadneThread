#!/usr/bin/env python3
"""
Optional: download the IBM AMLworld HI-Small synthetic dataset from Kaggle.

IMPORTANT (from the research phase):
  * The IBM AMLworld dataset is NOT freely redistributable. It is hosted on
    Kaggle under IBM's upload and is a research dataset without a permissive
    data license.
  * We therefore do NOT commit or redistribute it. This script lets a user who
    has Kaggle credentials download it locally for optional comparison.
  * The project's PRIMARY dataset is our own deterministic generator
    (scripts/generate_synthetic_fraud.py), which needs no external data.

Prerequisites:
    pip install kaggle
    export KAGGLE_USERNAME=... ; export KAGGLE_KEY=...   (or ~/.kaggle/kaggle.json)

Usage:
    python scripts/download_dataset.py [--out data/raw/ibm_amlworld]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

DATASET = "ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
FILES = [
    "HI-Small_Trans.csv",
    "HI-Small_Patterns.txt",
    "HI-Small_accounts.csv",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download IBM AMLworld HI-Small dataset from Kaggle (optional)"
    )
    parser.add_argument("--out", default="data/raw/ibm_amlworld", help="output directory")
    args = parser.parse_args()

    try:
        import kaggle  # noqa: F401
    except ImportError:
        print("The 'kaggle' package is not installed. Run: pip install kaggle")
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    print(f"Downloading {DATASET} to {args.out} ...")
    subprocess.run(
        ["kaggle", "datasets", "download", "-d", DATASET, "-p", args.out, "--unzip"],
        check=True,
    )
    print("Download complete. Files:")
    for f in FILES:
        p = os.path.join(args.out, f)
        print(f"  {'OK ' if os.path.exists(p) else 'MISSING'} {p}")


if __name__ == "__main__":
    main()
