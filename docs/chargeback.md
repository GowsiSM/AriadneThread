# Chargeback Evidence Responder

ML-powered chargeback evidence collection and response generation. This is a
*supplementary* layer on top of the deterministic graph detector — it never
changes detection decisions, it only packages evidence for card disputes.

## Overview

When a cardholder files a chargeback, the merchant must respond with evidence
proving (or refuting) the claim. This module:

1. **Predicts** per-transaction fraud risk using a trained XGBoost model
2. **Collects** evidence across six dimensions
3. **Prioritizes** evidence by chargeback reason code
4. **Generates** a structured response package with a recommendation

## Modules

### `backend/app/ml/predictor.py`

Loads the trained XGBoost model and preprocessor, produces a per-transaction
fraud risk score + level + explanation.

| Symbol | Purpose |
|---|---|
| `MLPredictor` | Loads model/preprocessor, predicts risk |
| `predict(transaction)` | Returns risk_score, risk_level, explanation |
| `available` | Whether the model loaded successfully |

- **Risk levels** — HIGH (> 0.7), MEDIUM (> 0.3), LOW
- **14 engineered features** matching the training pipeline
- **Graceful fallback** — deterministic heuristics if the model is unavailable

### `backend/app/ml/features.py`

Feature engineering matching the training pipeline.

### `backend/app/ml/explainer.py`

Lightweight feature attribution for prediction explanations.

### `backend/app/chargeback/evidence_engine.py`

Collects structured evidence for a chargeback case.

| Category | Description |
|---|---|
| transaction | The disputed transaction (amount, time, merchant) |
| customer | Cardholder's account history and profile |
| device | Device fingerprint / IP used for the transaction |
| authentication | 3DS / OTP / login signals |
| delivery | Shipping / fulfillment signals |
| ml_risk | ML fraud-probability signal |

The engine is deterministic and grounded in the data it is given. It never
fabricates evidence — if a signal is unknown, it is reported as "unknown".

### `backend/app/chargeback/evidence_priority.py`

Ranks collected evidence by relevance to the chargeback reason code.

| Reason | Priority |
|---|---|
| FRAUD / FRAUD_ACCOUNT_TAKEOVER | authentication, device, ml_risk, transaction, customer, delivery |
| NOT_RECEIVED / NOT_AS_DESCRIBED | delivery, transaction, customer, device, authentication, ml_risk |
| DUPLICATE / CANCELLED / others | transaction, customer, device, authentication, delivery, ml_risk |

### `backend/app/chargeback/response_generator.py`

Builds a structured response package.

| Field | Description |
|---|---|
| response_id | `RESP-{case_id}` |
| case_id | The chargeback case |
| recommendation | accept / contest / request more info |
| narrative | Human-readable summary |
| evidence | Prioritized evidence list |
| evidence_strength | Overall confidence score |
| generated_at | UTC timestamp |

**Recommendation logic:**
- **CONTEST** — fraud reasons (FRAUD, FRAUD_ACCOUNT_TAKEOVER) with strong evidence
- **ACCEPT** — service reasons (NOT_RECEIVED, NOT_AS_DESCRIBED, etc.) with strong evidence
- **REQUEST_MORE_INFO** — otherwise

### `backend/app/chargeback/case_manager.py`

In-memory case store loaded from `data/chargeback_cases.csv`.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/chargeback/predict` | Predict fraud risk for a transaction |
| GET | `/api/chargeback/cases` | List chargeback cases |
| POST | `/api/chargeback/cases` | Create a chargeback case |
| GET | `/api/chargeback/cases/{id}` | Case details |
| GET | `/api/chargeback/evidence/{id}` | Prioritized evidence |
| GET | `/api/chargeback/response/{id}` | Generated response package |

## Data

- `data/chargeback_cases.csv` — 120 synthetic cases (case_id, transaction_id,
  cardholder, merchant, amount, reason_code, reason_description, filed_at,
  status, priority, is_fraud)
- `models/fraud_model.pkl` — trained XGBoost model
- `models/preprocessor.pkl` — fitted preprocessor

## Frontend

- `/chargebacks` — list view with status filtering
- `/chargebacks/[id]` — detail view with prioritized evidence, recommendation,
  narrative, and evidence strength
