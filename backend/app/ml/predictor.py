"""
MLPredictor: loads the trained XGBoost fraud model and preprocessor, and
produces a per-transaction fraud risk score + level + explanation.

This is a *supplementary* layer on top of the deterministic graph detector.
It never replaces graph detection -- it only adds a per-transaction
fraud-probability signal used by the chargeback evidence responder.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import pandas as pd

from .features import add_features, select_features
from .explainer import explain_prediction

logger = logging.getLogger("fraud_sentinel.ml")

MODEL_PATH = Path(__file__).parent.parent.parent.parent / "models"
DATA_PATH = Path(__file__).parent.parent.parent.parent / "data"

# Risk-level thresholds (kept in sync with the explainer).
HIGH_THRESHOLD = 0.7
MEDIUM_THRESHOLD = 0.3


class MLPredictor:
    """Loads the trained model/preprocessor and predicts fraud risk."""

    def __init__(self, model_path: Path | None = None, preprocessor_path: Path | None = None):
        self.model_path = model_path or (MODEL_PATH / "fraud_model.pkl")
        self.preprocessor_path = preprocessor_path or (MODEL_PATH / "preprocessor.pkl")
        self.model = None
        self.preprocessor = None
        self._load()

    def _load(self) -> None:
        """Load model + preprocessor, tolerating missing files (graceful degrade)."""
        try:
            self.model = joblib.load(self.model_path)
            self.preprocessor = joblib.load(self.preprocessor_path)
            logger.info("ML predictor loaded from %s", self.model_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ML model unavailable (%s); predictions will be unavailable", exc)
            self.model = None
            self.preprocessor = None

    @property
    def available(self) -> bool:
        return self.model is not None and self.preprocessor is not None

    def predict(self, transaction: dict) -> dict:
        """Return fraud probability, risk level, and explanation for one transaction.

        If the model is unavailable, returns a deterministic fallback based on
        simple heuristics so the chargeback responder still has a risk signal.
        """
        if not self.available:
            return self._fallback_predict(transaction)

        try:
            df = pd.DataFrame([transaction])
            df = add_features(df)
            X = select_features(df)
            X_processed = self.preprocessor.transform(X)
            prob = float(self.model.predict_proba(X_processed)[0][1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("ML prediction failed (%s); using fallback", exc)
            return self._fallback_predict(transaction)

        risk_level = (
            "HIGH" if prob > HIGH_THRESHOLD
            else "MEDIUM" if prob > MEDIUM_THRESHOLD
            else "LOW"
        )

        # Build a feature dict for the explainer.
        feature_row = X.iloc[0].to_dict()

        return {
            "risk_score": prob,
            "risk_level": risk_level,
            "explanation": explain_prediction(feature_row, prob),
            "model_available": True,
        }

    def _fallback_predict(self, transaction: dict) -> dict:
        """Deterministic heuristic fallback when the ML model is unavailable."""
        amount = float(transaction.get("amt", transaction.get("amount", 0)) or 0)
        hour = 0
        raw_time = transaction.get("trans_date_trans_time", transaction.get("ts"))
        if raw_time:
            try:
                hour = pd.to_datetime(raw_time).hour
            except Exception:  # noqa: BLE001
                hour = 0

        score = 0.0
        reasons = []
        if amount > 10000:
            score += 0.4
            reasons.append("high amount")
        elif amount > 3000:
            score += 0.2
            reasons.append("elevated amount")
        if hour >= 22 or hour <= 5:
            score += 0.2
            reasons.append("night-time transaction")

        prob = min(score, 0.95)
        risk_level = (
            "HIGH" if prob > HIGH_THRESHOLD
            else "MEDIUM" if prob > MEDIUM_THRESHOLD
            else "LOW"
        )
        summary = (
            f"Heuristic fallback flags {risk_level} risk ({prob:.0%}). "
            + ("Drivers: " + ", ".join(reasons) + "." if reasons else "No dominant risk factors.")
        )
        return {
            "risk_score": prob,
            "risk_level": risk_level,
            "explanation": {
                "summary": summary,
                "top_factors": [{"feature": r, "detail": r, "weight": 0.3} for r in reasons],
                "risk_level": risk_level,
            },
            "model_available": False,
        }
