"""Chargeback Evidence Responder package.

This is a supplementary layer on top of the deterministic graph detector. It
adds ML-powered fraud risk scoring and chargeback evidence collection /
response generation for card disputes. It never replaces or modifies the
graph-based ring detection.
"""
from .case_manager import ChargebackCaseManager
from .evidence_engine import EvidenceEngine
from .evidence_priority import prioritize_evidence
from .response_generator import ResponseGenerator

__all__ = [
    "ChargebackCaseManager",
    "EvidenceEngine",
    "prioritize_evidence",
    "ResponseGenerator",
]
