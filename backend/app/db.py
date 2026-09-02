"""
Persistence layer with graceful degradation.

Tries to open a SQLite file at DATABASE_PATH. If the directory can't be
created/written (read-only filesystem, permissions issue, disk full), the
app falls back to an in-memory SQLite database and logs a clear warning
instead of crashing -- the demo and audit trail keep working, just without
durability across restarts.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger("fraud_sentinel.db")

Base = declarative_base()


class RingRecord(Base):
    __tablename__ = "rings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ring_id = Column(String, index=True)
    score = Column(Float)
    members = Column(JSON)
    signals = Column(JSON)
    explanation = Column(Text)
    explanation_source = Column(String)
    detected_at = Column(DateTime, default=datetime.utcnow)
    blast_radius = Column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)
    detail = Column(JSON)
    # --- Stage 5: extended audit fields ---
    actor = Column(String, default="system")
    ring_id = Column(String, nullable=True)
    case_id = Column(String, nullable=True)
    detector_version = Column(String, nullable=True)


class CaseRecord(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, unique=True, index=True)
    ring_id = Column(String, index=True)
    status = Column(String)  # CaseStatus value
    priority = Column(String)  # CasePriority value
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    members = Column(JSON)
    score = Column(Float)
    typology = Column(String, nullable=True)
    assigned_to = Column(String, nullable=True)
    notes = Column(JSON, default=list)
    evidence = Column(JSON, default=list)
    detector_version = Column(String, default="")
    dataset_version = Column(String, default="")
    detection_metadata = Column(JSON, default=dict)


class CaseEventRecord(Base):
    __tablename__ = "case_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, index=True)
    case_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=True)
    actor = Column(String)
    detail = Column(JSON, default=dict)


def build_engine():
    db_path = os.getenv("DATABASE_PATH", "./data/fraud_sentinel.db")
    try:
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        # touch the file to confirm it's actually writable
        with engine.connect() as conn:
            pass
        logger.info("Using SQLite at %s", db_path)
    except Exception as exc:
        logger.warning("Falling back to in-memory SQLite (reason: %s)", exc)
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    return SessionLocal()


def log_audit(
    event_type: str,
    detail: dict,
    actor: str = "system",
    ring_id: str | None = None,
    case_id: str | None = None,
    detector_version: str | None = None,
):
    session = get_session()
    try:
        session.add(AuditLog(
            event_type=event_type,
            detail=detail,
            ts=datetime.utcnow(),
            actor=actor,
            ring_id=ring_id,
            case_id=case_id,
            detector_version=detector_version,
        ))
        session.commit()
    except Exception as exc:
        logger.warning("Audit log write failed: %s", exc)
        session.rollback()
    finally:
        session.close()


def save_ring(ring: dict, explanation: dict, blast_radius: dict):
    session = get_session()
    try:
        rec = RingRecord(
            ring_id=ring["ring_id"],
            score=ring["score"],
            members=ring["members"],
            signals=ring["signals"],
            explanation=explanation["text"],
            explanation_source=explanation["source"],
            blast_radius=blast_radius,
        )
        session.add(rec)
        session.commit()
    except Exception as exc:
        logger.warning("Ring save failed: %s", exc)
        session.rollback()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Case persistence (Stage 5)
# ---------------------------------------------------------------------------

def _serialize_event(event) -> dict:
    """Serialize a CaseEvent (or dict) into a JSON-safe dict for persistence."""
    if isinstance(event, dict):
        return event
    return {
        "event_id": event.event_id,
        "case_id": event.case_id,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type,
        "from_status": event.from_status.value if event.from_status else None,
        "to_status": event.to_status.value if event.to_status else None,
        "actor": event.actor,
        "detail": event.detail,
    }


def save_case(case_dict: dict, events: list[dict] | None = None):
    """Persist an InvestigationCase (dict form) and optional events."""
    session = get_session()
    try:
        rec = CaseRecord(
            case_id=case_dict["case_id"],
            ring_id=case_dict["ring_id"],
            status=case_dict["status"],
            priority=case_dict["priority"],
            created_at=datetime.fromisoformat(case_dict["created_at"]),
            updated_at=datetime.fromisoformat(case_dict["updated_at"]),
            members=case_dict["members"],
            score=case_dict["score"],
            typology=case_dict.get("typology"),
            assigned_to=case_dict.get("assigned_to"),
            notes=case_dict.get("notes", []),
            evidence=case_dict.get("evidence", []),
            detector_version=case_dict.get("detector_version", ""),
            dataset_version=case_dict.get("dataset_version", ""),
            detection_metadata=case_dict.get("detection_metadata", {}),
        )
        session.merge(rec)
        session.commit()
    except Exception as exc:
        logger.warning("Case save failed: %s", exc)
        session.rollback()
    finally:
        session.close()

    if events:
        for ev in events:
            save_case_event(ev)


def save_case_event(event_dict: dict):
    """Persist a single CaseEvent."""
    session = get_session()
    try:
        from_status = event_dict.get("from_status")
        to_status = event_dict.get("to_status")
        rec = CaseEventRecord(
            event_id=event_dict["event_id"],
            case_id=event_dict["case_id"],
            timestamp=datetime.fromisoformat(event_dict["timestamp"]),
            event_type=event_dict["event_type"],
            from_status=from_status.value if hasattr(from_status, "value") else from_status,
            to_status=to_status.value if hasattr(to_status, "value") else to_status,
            actor=event_dict.get("actor", "system"),
            detail=event_dict.get("detail", {}),
        )
        session.merge(rec)
        session.commit()
    except Exception as exc:
        logger.warning("Case event save failed: %s", exc)
        session.rollback()
    finally:
        session.close()


def get_cases(status: str | None = None, limit: int = 50) -> list[dict]:
    """Retrieve cases from the database, optionally filtered by status."""
    session = get_session()
    try:
        q = session.query(CaseRecord)
        if status:
            q = q.filter(CaseRecord.status == status)
        rows = q.order_by(CaseRecord.updated_at.desc()).limit(limit).all()
        return [
            {
                "case_id": r.case_id,
                "ring_id": r.ring_id,
                "status": r.status,
                "priority": r.priority,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                "members": r.members,
                "score": r.score,
                "typology": r.typology,
                "assigned_to": r.assigned_to,
                "detector_version": r.detector_version,
                "dataset_version": r.dataset_version,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Case query failed: %s", exc)
        return []
    finally:
        session.close()


def get_case_events(case_id: str) -> list[dict]:
    """Retrieve the full event timeline for a case."""
    session = get_session()
    try:
        rows = (
            session.query(CaseEventRecord)
            .filter(CaseEventRecord.case_id == case_id)
            .order_by(CaseEventRecord.timestamp.asc())
            .all()
        )
        return [
            {
                "event_id": r.event_id,
                "case_id": r.case_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "event_type": r.event_type,
                "from_status": r.from_status,
                "to_status": r.to_status,
                "actor": r.actor,
                "detail": r.detail,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Case event query failed: %s", exc)
        return []
    finally:
        session.close()
