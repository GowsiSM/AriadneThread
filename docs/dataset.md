# Synthetic Fraud Ring Dataset

## Overview

The `backend/app/synthetic.py` module generates deterministic, reproducible fraud-ring
scenarios with ground-truth labels for evaluation. It is the **primary dataset** for the
Fraud Ring Sentinel system.

The `backend/app/data_gen.py` module is preserved for the streaming demo
and backward-compatible tests.

## Schema

### Users

| Column           | Type         | Description                   |
| ---------------- | ------------ | ----------------------------- |
| user_id          | string       | `USR-{random:06d}`            |
| name             | string       | Full name                     |
| risk_score       | float        | 0–1 user risk score           |
| account_age_days | int          | Days since account creation   |
| kyc_verified     | bool         | Whether KYC is verified       |
| device_ids       | list[string] | Associated device identifiers |
| ip_addresses     | list[string] | Associated IP addresses       |

### Transactions

| Column          | Type   | Description                                                        |
| --------------- | ------ | ------------------------------------------------------------------ |
| txn_id          | string | `TXN-{counter:06d}`                                                |
| sender_id       | string | Sender user_id                                                     |
| receiver_id     | string | Receiver user_id                                                   |
| amount          | float  | Transaction amount (INR)                                           |
| timestamp       | string | ISO 8601 with +05:30                                               |
| category        | string | `card_payment`, `upi`, `wallet`, `p2p_transfer`, `cash_withdrawal` |
| device_id       | string | Device used for the transaction                                    |
| ip_address      | string | IP used for the transaction                                        |
| geo_distance_km | float  | Distance between sender/receiver (km)                              |

### Ground Truth

| Column          | Type                  | Description                         |
| --------------- | --------------------- | ----------------------------------- |
| scenario_id     | string                | `SCN-{index:03d}`                   |
| typology        | string                | One of the 12 typologies            |
| ring_id         | string                | `RING-{index:03d}`                  |
| user_ids        | list[string]          | Users in the ring                   |
| txn_ids         | list[string]          | Transactions in the ring            |
| roles           | dict[string → string] | User role assignments               |
| difficulty      | string                | `easy`, `medium`, or `hard`         |
| detection_hints | dict                  | Typology-specific detection signals |

## Fraud Typologies (12)

| #   | Typology      | Description                                     | Difficulty |
| --- | ------------- | ----------------------------------------------- | ---------- |
| 1   | circular      | A→B→C→A money loop                              | easy       |
| 2   | fan_in        | Multiple senders → one receiver                 | easy       |
| 3   | fan_out       | One sender → multiple receivers                 | easy       |
| 4   | smurfing      | Many small transactions below threshold         | hard       |
| 5   | layering      | Multi-hop chain: originator → mules → collector | hard       |
| 6   | funnel        | fan_in then fan_out                             | medium     |
| 7   | mule_chain    | Long chain of intermediate accounts             | medium     |
| 8   | burst         | Rapid burst of transactions in short window     | easy       |
| 9   | shared_device | Multiple users share same device                | medium     |
| 10  | shared_ip     | Multiple users share same IP address            | medium     |
| 11  | pass_through  | Money flows through without retention           | medium     |
| 12  | multi_hop     | 5-hop chain with collateral edges               | hard       |

## Roles

| Role         | Description                       |
| ------------ | --------------------------------- |
| originator   | Initiates the fraud chain         |
| mule         | Passes money through              |
| intermediary | Intermediate relay                |
| collector    | Collects and consolidates funds   |
| funnel       | Receives fan_in and sends fan_out |
| beneficiary  | Final recipient                   |

## Generation

```bash
# Generate default dataset (200+ transactions, deterministic seed)
python scripts/generate_synthetic_fraud.py

# Custom size and seed
python scripts/generate_synthetic_fraud.py --size 500 --seed 42
```

### Output Files (in `data/processed/`)

| File              | Description                                                           |
| ----------------- | --------------------------------------------------------------------- |
| transactions.csv  | Transactions with ground-truth columns **removed** (no label leakage) |
| users.csv         | User profiles                                                         |
| ground_truth.json | Separated ground-truth labels (scenario_id, ring_id, typology, role)  |
| dataset_meta.json | Generation metadata (seed, timestamp, version, SHA256 hashes)         |

### Label Leakage Prevention

The generator separates ground-truth labels (`is_fraud_ring_member`, `ring_id`, `typology`,
`role`) from the transaction data before writing `transactions.csv`. This prevents models
from leaking on these columns. The ground truth is stored in a separate `ground_truth.json`
for evaluation only.

## External Data (Optional)

For additional realism, an optional IBM AMLworld dataset can be downloaded:

```bash
# Requires Kaggle CLI credentials
python scripts/download_dataset.py --kaggle-json ~/.kaggle/kaggle.json

# Normalize into our schema
python scripts/prepare_dataset.py data/raw/ibm_amlworld/ data/processed/external/
```

## Evaluation Protocol

Per the brief (section 17), the evaluation pipeline uses:

1. **Held-out synthetic rings** (12 scenarios) — full evaluation with ground truth
2. **Held-out public data** (if IBM AMLworld available) — additional validation
3. **Constructive counterfactuals** (Stage 6) — adversarial testing
4. **Temporal split** — train on T-30d, test on T-0d

Evaluation metrics: Precision ≥ 0.80, Recall ≥ 0.60, F1 ≥ 0.65, Explanation faithfulness ≥ 0.90.

## Version

Current: `1.0.0`
Change log: `CHANGELOG.md`
