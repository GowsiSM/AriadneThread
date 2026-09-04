"""
ChargebackCaseManager: in-memory lifecycle management for chargeback cases.

Loads chargeback cases from data/chargeback_cases.csv and tracks their status
(OPEN -> UNDER_REVIEW -> RESPONDED -> CLOSED) plus any analyst notes. This is
a lightweight, in-process store (fine for an MVP single-worker demo), separate
from the graph-detection CaseManager in app/investigation.py.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("fraud_sentinel.chargeback")

ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = ROOT / "data"
CASES_CSV = DATA_DIR / "chargeback_cases.csv"

VALID_STATUSES = {"OPEN", "UNDER_REVIEW", "RESPONDED", "CLOSED"}


class ChargebackCaseManager:
    """Loads and manages chargeback cases in memory."""

    def __init__(self, csv_path: Path | None = None):
        self.csv_path = csv_path or CASES_CSV
        self.cases: dict[str, dict] = {}
        self.notes: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        """Load chargeback cases from CSV into memory."""
        if not self.csv_path.exists():
            logger.warning("Chargeback cases file not found: %s", self.csv_path)
            return
        try:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    case_id = row.get("case_id", "")
                    if not case_id:
                        continue
                    self.cases[case_id] = {
                        "case_id": case_id,
                        "transaction_id": row.get("transaction_id", ""),
                        "cardholder": row.get("cardholder", ""),
                        "merchant": row.get("merchant", ""),
                        "amount": float(row.get("amount", 0) or 0),
                        "reason_code": row.get("reason_code", ""),
                        "reason_description": row.get("reason_description", ""),
                        "filed_at": row.get("filed_at", ""),
                        "status": row.get("status", "OPEN"),
                        "priority": row.get("priority", "LOW"),
                        "is_fraud": int(row.get("is_fraud", 0) or 0),
                    }
            logger.info("Loaded %d chargeback cases", len(self.cases))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load chargeback cases: %s", exc)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_cases(self, status: str | None = None) -> list[dict]:
        cases = list(self.cases.values())
        if status:
            cases = [c for c in cases if c["status"] == status]
        # Sort by priority (CRITICAL first) then filed_at.
        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        cases.sort(key=lambda c: (priority_order.get(c.get("priority", "LOW"), 3), c.get("filed_at", "")))
        return cases

    def get_case(self, case_id: str) -> dict | None:
        case = self.cases.get(case_id)
        if case is None:
            return None
        result = dict(case)
        result["notes"] = self.notes.get(case_id, [])
        return result

    def summary(self) -> dict:
        by_status = {}
        by_priority = {}
        for c in self.cases.values():
            by_status[c["status"]] = by_status.get(c["status"], 0) + 1
            by_priority[c["priority"]] = by_priority.get(c["priority"], 0) + 1
        return {
            "total_cases": len(self.cases),
            "by_status": by_status,
            "by_priority": by_priority,
            "open_cases": by_status.get("OPEN", 0) + by_status.get("UNDER_REVIEW", 0),
            "closed_cases": by_status.get("CLOSED", 0),
        }

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_case(self, case: dict) -> dict:
        """Create a new chargeback case and return it."""
        case_id = case.get("case_id") or f"CB-{len(self.cases) + 1:04d}"
        self.cases[case_id] = {
            "case_id": case_id,
            "transaction_id": case.get("transaction_id", ""),
            "cardholder": case.get("cardholder", ""),
            "merchant": case.get("merchant", ""),
            "amount": float(case.get("amount", 0) or 0),
            "reason_code": case.get("reason_code", ""),
            "reason_description": case.get("reason_description", ""),
            "filed_at": case.get("filed_at", datetime.now(timezone.utc).isoformat()),
            "status": case.get("status", "OPEN"),
            "priority": case.get("priority", "LOW"),
            "is_fraud": int(case.get("is_fraud", 0) or 0),
        }
        self._add_note(case_id, "Case created", "system")
        return self.get_case(case_id)

    def update_status(self, case_id: str, to_status: str, actor: str = "analyst") -> dict | None:
        """Transition a case to a new status. Returns None on invalid input."""
        if case_id not in self.cases:
            return None
        if to_status not in VALID_STATUSES:
            return None
        return self.transition(case_id, to_status, actor)

    def transition(self, case_id: str, to_status: str, actor: str = "analyst") -> dict:
        if case_id not in self.cases:
            raise KeyError(case_id)
        if to_status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {to_status}")
        self.cases[case_id]["status"] = to_status
        self._add_note(case_id, f"Status changed to {to_status}", actor)
        return self.get_case(case_id)

    def add_note(self, case_id: str, note: str, actor: str = "analyst") -> dict:
        if case_id not in self.cases:
            raise KeyError(case_id)
        self._add_note(case_id, note, actor)
        return self.get_case(case_id)

    def _add_note(self, case_id: str, note: str, actor: str) -> None:
        self.notes.setdefault(case_id, []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "note": note,
        })
