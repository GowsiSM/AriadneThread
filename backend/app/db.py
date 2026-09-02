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


def log_audit(event_type: str, detail: dict):
    session = get_session()
    try:
        session.add(AuditLog(event_type=event_type, detail=detail, ts=datetime.utcnow()))
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
