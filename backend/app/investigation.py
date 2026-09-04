"""
Investigation case management for AriadneThread.

Implements the investigation workflow from the brief (Section 3.9):
  - CaseStatus lifecycle: OBSERVED -> SUSPICIOUS -> HIGH_RISK -> UNDER_REVIEW
    -> CONFIRMED / DISMISSED / RESOLVED
  - State machine with validated transitions
  - Auto-creation from detection results
  - Priority scoring
  - Timeline / audit trail per case

References: Tracer (C) case files, NEXUS (F) audit trail.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("fraud_sentinel.investigation")


# ---------------------------------------------------------------------------
# Case status enum + lifecycle
# ---------------------------------------------------------------------------

class CaseStatus(str, enum.Enum):
    OBSERVED = "OBSERVED"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"
    RESOLVED = "RESOLVED"


# Terminal states — no further transitions allowed.
TERMINAL_STATES: set[CaseStatus] = {
    CaseStatus.CONFIRMED,
    CaseStatus.DISMISSED,
    CaseStatus.RESOLVED,
}

# Valid transitions: from_state -> set of allowed to_states.
# Based on the brief's lifecycle with one addition: HIGH_RISK -> CONFIRMED
# (fast-track for obvious rings) and UNDER_REVIEW -> RESOLVED (ring is now
# handled, even if not formally confirmed as fraud).
VALID_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.OBSERVED: {CaseStatus.SUSPICIOUS, CaseStatus.DISMISSED},
    CaseStatus.SUSPICIOUS: {CaseStatus.HIGH_RISK, CaseStatus.UNDER_REVIEW, CaseStatus.DISMISSED},
    CaseStatus.HIGH_RISK: {CaseStatus.UNDER_REVIEW, CaseStatus.CONFIRMED, CaseStatus.DISMISSED},
    CaseStatus.UNDER_REVIEW: {CaseStatus.CONFIRMED, CaseStatus.DISMISSED, CaseStatus.RESOLVED},
    CaseStatus.CONFIRMED: set(),
    CaseStatus.DISMISSED: set(),
    CaseStatus.RESOLVED: set(),
}


def valid_transition(from_status: CaseStatus, to_status: CaseStatus) -> bool:
    """Check whether a lifecycle transition is allowed."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

class CasePriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


def compute_priority(score: float, n_members: int, typology: str | None) -> CasePriority:
    """Deterministic priority from detection metadata.

    Priority rules:
      - score >= 80 OR (typology in high_risk AND score >= 65) -> CRITICAL
      - score >= 65 OR n_members >= 10 -> HIGH
      - score >= 55 -> MEDIUM
      - else -> LOW
    """
    high_risk_typologies = {"circular", "layering", "mule_chain", "smurfing"}
    is_high_risk_typology = typology in high_risk_typologies if typology else False

    if score >= 80 or (is_high_risk_typology and score >= 65):
        return CasePriority.CRITICAL
    if score >= 65 or n_members >= 10:
        return CasePriority.HIGH
    if score >= 55:
        return CasePriority.MEDIUM
    return CasePriority.LOW


# ---------------------------------------------------------------------------
# Case event (for timeline / audit trail)
# ---------------------------------------------------------------------------

@dataclass
class CaseEvent:
    """A single lifecycle event for a case."""
    event_id: str
    case_id: str
    timestamp: datetime
    event_type: str  # "status_change", "note_added", "assigned", "evidence_added", "created"
    from_status: CaseStatus | None
    to_status: CaseStatus | None
    actor: str  # "system" or analyst name/id
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Investigation case
# ---------------------------------------------------------------------------

@dataclass
class InvestigationCase:
    """An investigation case wrapping a ring candidate."""
    case_id: str
    ring_id: str
    status: CaseStatus
    priority: CasePriority
    created_at: datetime
    updated_at: datetime
    members: list[str]
    score: float
    typology: str | None
    assigned_to: str | None
    notes: list[str]
    evidence: list[dict[str, Any]]
    events: list[CaseEvent]
    detector_version: str = ""
    dataset_version: str = ""
    detection_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "ring_id": self.ring_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "members": self.members,
            "score": self.score,
            "typology": self.typology,
            "assigned_to": self.assigned_to,
            "notes": self.notes,
            "evidence": self.evidence,
            "n_events": len(self.events),
            "detector_version": self.detector_version,
            "dataset_version": self.dataset_version,
        }


# ---------------------------------------------------------------------------
# Case manager (in-memory, pure-logic layer)
# ---------------------------------------------------------------------------

class CaseManager:
    """In-memory case manager.

    Handles state machine enforcement, event recording, and timeline
    queries.  Persistence is handled by db.py (SQLAlchemy); this layer
    is a pure-logic intermediary that can also be used standalone for
    testing.
    """

    def __init__(self) -> None:
        self._cases: dict[str, InvestigationCase] = {}
        self._ring_to_case: dict[str, str] = {}  # ring_id -> case_id
        self._counter: int = 0

    # --- case creation ---

    def create_case(
        self,
        ring_id: str,
        members: list[str],
        score: float,
        typology: str | None = None,
        assigned_to: str | None = None,
        detector_version: str = "",
        dataset_version: str = "",
        detection_metadata: dict[str, Any] | None = None,
    ) -> InvestigationCase:
        """Create a new investigation case from a detection result.

        Initial status is OBSERVED. Priority is computed from score/typology.
        """
        if ring_id in self._ring_to_case:
            existing_id = self._ring_to_case[ring_id]
            return self._cases[existing_id]

        self._counter += 1
        case_id = f"INV-{self._counter:04d}"
        now = datetime.utcnow()

        priority = compute_priority(score, len(members), typology)
        status = CaseStatus.OBSERVED

        # If score is very high, skip straight to HIGH_RISK
        if score >= 80:
            status = CaseStatus.HIGH_RISK

        case = InvestigationCase(
            case_id=case_id,
            ring_id=ring_id,
            status=status,
            priority=priority,
            created_at=now,
            updated_at=now,
            members=list(members),
            score=score,
            typology=typology,
            assigned_to=assigned_to,
            notes=[],
            evidence=[],
            events=[],
            detector_version=detector_version,
            dataset_version=dataset_version,
            detection_metadata=detection_metadata or {},
        )

        # Record creation event
        event = CaseEvent(
            event_id=f"EVT-{case_id}-000",
            case_id=case_id,
            timestamp=now,
            event_type="created",
            from_status=None,
            to_status=status,
            actor="system",
            detail={
                "ring_id": ring_id,
                "score": score,
                "typology": typology,
                "n_members": len(members),
                "priority": priority.value,
            },
        )
        case.events.append(event)

        self._cases[case_id] = case
        self._ring_to_case[ring_id] = case_id

        logger.info(
            "Created case %s for ring %s (score=%.1f, status=%s, priority=%s)",
            case_id, ring_id, score, status.value, priority.value,
        )
        return case

    # --- case lookup ---

    def get_case(self, case_id: str) -> InvestigationCase | None:
        return self._cases.get(case_id)

    def get_case_by_ring(self, ring_id: str) -> InvestigationCase | None:
        cid = self._ring_to_case.get(ring_id)
        return self._cases.get(cid) if cid else None

    def list_cases(
        self,
        status: CaseStatus | None = None,
        priority: CasePriority | None = None,
    ) -> list[InvestigationCase]:
        """List cases, optionally filtered by status and/or priority."""
        cases = list(self._cases.values())
        if status is not None:
            cases = [c for c in cases if c.status == status]
        if priority is not None:
            cases = [c for c in cases if c.priority == priority]
        return sorted(cases, key=lambda c: c.updated_at, reverse=True)

    # --- state transitions ---

    def transition(
        self,
        case_id: str,
        to_status: CaseStatus,
        actor: str = "analyst",
        detail: dict[str, Any] | None = None,
    ) -> InvestigationCase:
        """Attempt a lifecycle transition. Raises ValueError if invalid."""
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id} not found")

        from_status = case.status

        if from_status in TERMINAL_STATES:
            raise ValueError(
                f"Case {case_id} is in terminal state {from_status.value}; "
                "no further transitions allowed"
            )

        if not valid_transition(from_status, to_status):
            raise ValueError(
                f"Invalid transition: {from_status.value} -> {to_status.value}. "
                f"Allowed: {[s.value for s in VALID_TRANSITIONS.get(from_status, set())]}"
            )

        now = datetime.utcnow()
        case.status = to_status
        case.updated_at = now

        event_num = len(case.events)
        event = CaseEvent(
            event_id=f"EVT-{case_id}-{event_num:03d}",
            case_id=case_id,
            timestamp=now,
            event_type="status_change",
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            detail=detail or {},
        )
        case.events.append(event)

        logger.info(
            "Case %s: %s -> %s (by %s)", case_id, from_status.value, to_status.value, actor,
        )
        return case

    # --- notes and evidence ---

    def add_note(self, case_id: str, note: str, actor: str = "analyst") -> CaseEvent:
        """Add a note to a case."""
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id} not found")

        now = datetime.utcnow()
        case.notes.append(note)
        case.updated_at = now

        event_num = len(case.events)
        event = CaseEvent(
            event_id=f"EVT-{case_id}-{event_num:03d}",
            case_id=case_id,
            timestamp=now,
            event_type="note_added",
            from_status=case.status,
            to_status=None,
            actor=actor,
            detail={"note": note},
        )
        case.events.append(event)
        return event

    def add_evidence(self, case_id: str, evidence: dict[str, Any], actor: str = "system") -> CaseEvent:
        """Attach evidence (e.g., transaction IDs, graph snapshots) to a case."""
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id} not found")

        now = datetime.utcnow()
        case.evidence.append(evidence)
        case.updated_at = now

        event_num = len(case.events)
        event = CaseEvent(
            event_id=f"EVT-{case_id}-{event_num:03d}",
            case_id=case_id,
            timestamp=now,
            event_type="evidence_added",
            from_status=case.status,
            to_status=None,
            actor=actor,
            detail=evidence,
        )
        case.events.append(event)
        return event

    def assign(self, case_id: str, analyst: str) -> CaseEvent:
        """Assign a case to an analyst."""
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id} not found")

        now = datetime.utcnow()
        old_assignee = case.assigned_to
        case.assigned_to = analyst
        case.updated_at = now

        event_num = len(case.events)
        event = CaseEvent(
            event_id=f"EVT-{case_id}-{event_num:03d}",
            case_id=case_id,
            timestamp=now,
            event_type="assigned",
            from_status=case.status,
            to_status=None,
            actor="system",
            detail={"assigned_to": analyst, "previous": old_assignee},
        )
        case.events.append(event)
        return event

    # --- timeline ---

    def get_timeline(self, case_id: str) -> list[dict]:
        """Return the full event timeline for a case, oldest first."""
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id} not found")

        timeline = []
        for e in case.events:
            timeline.append({
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "from_status": e.from_status.value if e.from_status else None,
                "to_status": e.to_status.value if e.to_status else None,
                "actor": e.actor,
                "detail": e.detail,
            })
        return timeline

    # --- summary stats ---

    def summary(self) -> dict:
        """Summary statistics for the case manager."""
        all_cases = list(self._cases.values())
        by_status = {}
        by_priority = {}
        for c in all_cases:
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
            by_priority[c.priority.value] = by_priority.get(c.priority.value, 0) + 1

        return {
            "total_cases": len(all_cases),
            "by_status": by_status,
            "by_priority": by_priority,
            "open_cases": sum(1 for c in all_cases if c.status not in TERMINAL_STATES),
            "closed_cases": sum(1 for c in all_cases if c.status in TERMINAL_STATES),
        }


# ---------------------------------------------------------------------------
# Auto-create from detection candidates
# ---------------------------------------------------------------------------

def auto_create_cases(
    manager: CaseManager,
    candidates: list,
    score_threshold: float = 55.0,
    detector_version: str = "",
    dataset_version: str = "",
) -> list[InvestigationCase]:
    """Auto-create or update cases for candidates above threshold.

    Returns the list of cases that were created or updated.
    """
    created = []
    for cand in candidates:
        if cand.score < score_threshold:
            continue

        # Check if case already exists for this ring
        existing = manager.get_case_by_ring(cand.ring_id)
        if existing is not None:
            # Update score if detection produced a new (higher) score
            if cand.score > existing.score:
                existing.score = cand.score
                existing.updated_at = datetime.utcnow()
                manager.add_evidence(
                    existing.case_id,
                    {"type": "score_update", "new_score": cand.score},
                    actor="system",
                )
            created.append(existing)
            continue

        case = manager.create_case(
            ring_id=cand.ring_id,
            members=cand.members,
            score=cand.score,
            typology=cand.typology,
            detector_version=detector_version,
            dataset_version=dataset_version,
            detection_metadata={
                "typology_confidence": cand.typology_confidence,
                "n_roles": len(cand.roles),
                "n_motifs": len(cand.motifs),
                "n_sub_rings": len(cand.sub_rings),
            },
        )

        # Attach initial evidence from detection
        if cand.motifs:
            manager.add_evidence(
                case.case_id,
                {
                    "type": "detected_motifs",
                    "motifs": [{"type": m.motif_type, "evidence": m.evidence} for m in cand.motifs],
                },
                actor="system",
            )
        if cand.flow_summary:
            manager.add_evidence(
                case.case_id,
                {
                    "type": "flow_summary",
                    "total_inflow": cand.flow_summary.total_inflow,
                    "total_outflow": cand.flow_summary.total_outflow,
                    "flow_ratio": cand.flow_summary.flow_ratio,
                    "concentration": cand.flow_summary.concentration,
                },
                actor="system",
            )

        created.append(case)

    return created
