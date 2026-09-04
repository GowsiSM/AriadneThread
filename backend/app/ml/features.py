"""
Feature engineering for the ML chargeback predictor.

These functions mirror the feature construction used in scripts/train_model.py
so that a single transaction dict passed to the predictor produces exactly the
same feature vector the XGBoost model was trained on.

The model is a *supplementary* layer on top of the deterministic graph
detector. It never replaces graph detection -- it only adds a per-transaction
fraud-probability signal used by the chargeback evidence responder.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

# The exact feature columns the model was trained on (see train_model.py).
FEATURE_COLUMNS = [
    "amt",
    "log_amount",
    "hour",
    "day_of_week",
    "month",
    "is_night",
    "lat",
    "long",
    "merch_lat",
    "merch_long",
    "city_pop",
    "customer_frequency",
    "merchant_frequency",
    "category",
]


def _parse_time(raw) -> datetime:
    """Parse a transaction timestamp into a datetime, tolerating ISO or epoch."""
    if raw is None:
        return datetime.utcnow()
    if isinstance(raw, (int, float)):
        return datetime.utcfromtimestamp(raw)
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return datetime.utcnow()


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features to a DataFrame of raw transactions.

    The input DataFrame must contain at least: amt, trans_date_trans_time (or
    ts), lat, long, merch_lat, merch_long, city_pop, category, cc_num (or
    sender), merchant (or receiver). Missing optional columns are filled with
    safe defaults so a partial payload still produces a valid feature vector.
    """
    df = df.copy()

    # --- Time features ---
    time_col = "trans_date_trans_time" if "trans_date_trans_time" in df.columns else "ts"
    if time_col in df.columns:
        parsed = df[time_col].map(_parse_time)
    else:
        parsed = pd.Series([datetime.utcnow()] * len(df))
    df["hour"] = parsed.dt.hour
    df["day_of_week"] = parsed.dt.dayofweek
    df["month"] = parsed.dt.month
    df["is_night"] = ((df["hour"] >= 22) | (df["hour"] <= 5)).astype(int)

    # --- Amount features ---
    df["amt"] = pd.to_numeric(df.get("amt", 0), errors="coerce").fillna(0.0)
    df["log_amount"] = df["amt"].map(lambda x: math.log1p(max(float(x), 0.0)))

    # --- Location features (default to 0 if absent) ---
    for col in ("lat", "long", "merch_lat", "merch_long", "city_pop"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # --- Frequency features ---
    # customer_frequency: how many times this card/account appears in the batch.
    cust_col = "cc_num" if "cc_num" in df.columns else "sender"
    merch_col = "merchant" if "merchant" in df.columns else "receiver"
    if cust_col in df.columns:
        df["customer_frequency"] = df.groupby(cust_col)[cust_col].transform("count")
    else:
        df["customer_frequency"] = 1
    if merch_col in df.columns:
        df["merchant_frequency"] = df.groupby(merch_col)[merch_col].transform("count")
    else:
        df["merchant_frequency"] = 1

    # --- Category (categorical, one-hot encoded by the preprocessor) ---
    if "category" not in df.columns:
        df["category"] = "unknown"

    return df


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the columns the model expects, in training order."""
    out = pd.DataFrame()
    for col in FEATURE_COLUMNS:
        out[col] = df[col] if col in df.columns else 0
    return out
