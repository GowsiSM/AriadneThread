"""
Local explanation for a single ML fraud prediction.

We deliberately avoid a hard dependency on the `shap` package (it is heavy and
can be slow to import). Instead we produce a lightweight, deterministic
"feature attribution" by comparing each feature's value against a reference
baseline and reporting the features that most plausibly drove the score up.

This is a *supplementary* explanation for the chargeback evidence responder --
it never influences the deterministic graph detector's decisions.
"""
from __future__ import annotations

from .features import FEATURE_COLUMNS

# Human-readable labels for the model's features.
FEATURE_LABELS = {
    "amt": "Transaction amount",
    "log_amount": "Log transaction amount",
    "hour": "Hour of day",
    "day_of_week": "Day of week",
    "month": "Month",
    "is_night": "Night-time transaction",
    "lat": "Cardholder latitude",
    "long": "Cardholder longitude",
    "merch_lat": "Merchant latitude",
    "merch_long": "Merchant longitude",
    "city_pop": "City population",
    "customer_frequency": "Cardholder transaction frequency",
    "merchant_frequency": "Merchant transaction frequency",
    "category": "Merchant category",
}

# Features that, when elevated, tend to push fraud probability up.
RISK_ELEVATING = {
    "amt", "log_amount", "is_night", "customer_frequency", "merchant_frequency",
}


def explain_prediction(features: dict, probability: float) -> dict:
    """Return a short, human-readable explanation of an ML fraud prediction.

    Args:
        features: the engineered feature dict for the transaction.
        probability: the model's fraud probability (0..1).

    Returns:
        A dict with `summary`, `top_factors`, and `risk_level`.
    """
    factors = []
    for col in FEATURE_COLUMNS:
        if col not in features:
            continue
        label = FEATURE_LABELS.get(col, col.replace("_", " "))
        value = features[col]

        # Night-time transactions are a strong fraud signal.
        if col == "is_night" and value:
            factors.append((label, "transaction occurred at night", 0.6))
        # High amounts elevate risk.
        if col == "amt" and isinstance(value, (int, float)) and value > 5000:
            factors.append((label, f"unusually high amount ({value:,.0f})", 0.5))
        # High frequency on a single card/merchant can indicate automated fraud.
        if col == "customer_frequency" and isinstance(value, (int, float)) and value > 5:
            factors.append((label, f"high cardholder frequency ({int(value)} tx)", 0.4))
        if col == "merchant_frequency" and isinstance(value, (int, float)) and value > 5:
            factors.append((label, f"high merchant frequency ({int(value)} tx)", 0.4))

    # Sort by weight descending, keep top 3.
    factors.sort(key=lambda f: f[2], reverse=True)
    top_factors = [{"feature": f[0], "detail": f[1], "weight": f[2]} for f in factors[:3]]

    if probability >= 0.7:
        risk_level = "HIGH"
    elif probability >= 0.3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if top_factors:
        summary = (
            f"ML model flags {risk_level} fraud risk ({probability:.0%}). "
            + "Key drivers: " + "; ".join(f"{f['feature']} ({f['detail']})" for f in top_factors) + "."
        )
    else:
        summary = f"ML model flags {risk_level} fraud risk ({probability:.0%}) with no dominant risk factors."

    return {
        "summary": summary,
        "top_factors": top_factors,
        "risk_level": risk_level,
    }
