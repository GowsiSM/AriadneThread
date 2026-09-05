"""
Tests for Stage 5: investigation case management + versioning.
"""
import pytest

from app.investigation import (
    CaseManager,
    CaseStatus,
    CasePriority,
    compute_priority,
    valid_transition,
    auto_create_cases,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
)
from app.versions import (
    DetectorVersion,
    DatasetVersion,
    FeatureVersion,
    RunVersion,
    SIGNAL_WEIGHTS,
    DEFAULT_THRESHOLD,
    ENABLED_FEATURES,
    log_versions,
)


# ---------------------------------------------------------------------------
# Versioning tests
# ---------------------------------------------------------------------------

class TestVersioning:
    def test_detector_version_deterministic(self):
        v1 = DetectorVersion.compute()
        v2 = DetectorVersion.compute()
        assert v1.hash == v2.hash
        assert v1.short == v2.short

    def test_detector_version_changes_with_weights(self):
        v1 = DetectorVersion.compute()
        v2 = DetectorVersion.compute(weights={"cycle_involvement": 0.5, "community_isolation": 0.5})
        assert v1.hash != v2.hash

    def test_detector_version_changes_with_threshold(self):
        v1 = DetectorVersion.compute()
        v2 = DetectorVersion.compute(threshold=60.0)
        assert v1.hash != v2.hash

    def test_detector_version_changes_with_features(self):
        v1 = DetectorVersion.compute()
        v2 = DetectorVersion.compute(features=["cycle_detection"])
        assert v1.hash != v2.hash

    def test_dataset_version_deterministic(self):
        v1 = DatasetVersion.compute()
        v2 = DatasetVersion.compute()
        assert v1.hash == v2.hash

    def test_dataset_version_changes_with_config(self):
        v1 = DatasetVersion.compute()
        v2 = DatasetVersion.compute({"n_rings": 5, "seed": 99})
        assert v1.hash != v2.hash

    def test_feature_version_deterministic(self):
        v1 = FeatureVersion.compute()
        v2 = FeatureVersion.compute()
        assert v1.hash == v2.hash

    def test_feature_version_changes_with_features(self):
        v1 = FeatureVersion.compute()
        v2 = FeatureVersion.compute(["motif_detection"])
        assert v1.hash != v2.hash

    def test_run_version_combines_all(self):
        det = DetectorVersion.compute()
        ds = DatasetVersion.compute()
        feat = FeatureVersion.compute()
        run = RunVersion(det, ds, feat)
        assert run.combined_hash
        assert run.short.startswith("run-")

    def test_run_version_deterministic(self):
        det = DetectorVersion.compute()
        ds = DatasetVersion.compute()
        feat = FeatureVersion.compute()
        r1 = RunVersion(det, ds, feat)
        r2 = RunVersion(det, ds, feat)
        assert r1.combined_hash == r2.combined_hash

    def test_log_versions_contains_all_keys(self):
        v = log_versions()
        assert "detector_version" in v
        assert "dataset_version" in v
        assert "feature_version" in v
        assert "run_version" in v
        assert "signal_weights" in v
        assert "threshold" in v
        assert "features" in v
        assert "dataset_config" in v

    def test_signal_weights_sum_to_one(self):
        total = sum(SIGNAL_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6

    def test_default_threshold_matches_detection(self):
        # Must match SCORE_THRESHOLD in app/main.py (40.0) so the Versions
        # page, README metrics table, and the live detector all agree.
        assert DEFAULT_THRESHOLD == 40.0

    def test_enabled_features_nonempty(self):
        assert len(ENABLED_FEATURES) > 0


# ---------------------------------------------------------------------------
# Priority tests
# ---------------------------------------------------------------------------

class TestPriority:
    def test_critical_high_score(self):
        assert compute_priority(85.0, 5, "circular") == CasePriority.CRITICAL

    def test_critical_high_risk_typology(self):
        assert compute_priority(70.0, 5, "layering") == CasePriority.CRITICAL

    def test_high_score(self):
            assert compute_priority(60.0, 5, "fan_in") == CasePriority.HIGH

    def test_high_member_count(self):
        assert compute_priority(60.0, 12, None) == CasePriority.HIGH

    def test_medium(self):
        assert compute_priority(50.0, 5, None) == CasePriority.MEDIUM

    def test_low(self):
        assert compute_priority(42.0, 3, None) == CasePriority.LOW

    def test_high_risk_typology_below_threshold_is_not_critical(self):
        # score 50 < 65, so not CRITICAL and not HIGH -> MEDIUM
        assert compute_priority(50.0, 5, "circular") == CasePriority.MEDIUM


# ---------------------------------------------------------------------------
# State machine tests
# ---------------------------------------------------------------------------

class TestStateMachine:
    def test_valid_transition_observed_to_suspicious(self):
        assert valid_transition(CaseStatus.OBSERVED, CaseStatus.SUSPICIOUS)

    def test_valid_transition_observed_to_dismissed(self):
        assert valid_transition(CaseStatus.OBSERVED, CaseStatus.DISMISSED)

    def test_invalid_transition_observed_to_confirmed(self):
        assert not valid_transition(CaseStatus.OBSERVED, CaseStatus.CONFIRMED)

    def test_valid_transition_suspicious_to_high_risk(self):
        assert valid_transition(CaseStatus.SUSPICIOUS, CaseStatus.HIGH_RISK)

    def test_valid_transition_high_risk_to_under_review(self):
        assert valid_transition(CaseStatus.HIGH_RISK, CaseStatus.UNDER_REVIEW)

    def test_valid_transition_under_review_to_confirmed(self):
        assert valid_transition(CaseStatus.UNDER_REVIEW, CaseStatus.CONFIRMED)

    def test_valid_transition_under_review_to_dismissed(self):
        assert valid_transition(CaseStatus.UNDER_REVIEW, CaseStatus.DISMISSED)

    def test_valid_transition_under_review_to_resolved(self):
        assert valid_transition(CaseStatus.UNDER_REVIEW, CaseStatus.RESOLVED)

    def test_terminal_states_have_no_transitions(self):
        for s in TERMINAL_STATES:
            assert VALID_TRANSITIONS[s] == set()

    def test_all_statuses_have_entries(self):
        for s in CaseStatus:
            assert s in VALID_TRANSITIONS


# ---------------------------------------------------------------------------
# CaseManager tests
# ---------------------------------------------------------------------------

class TestCaseManager:
    def test_create_case(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1", "F2", "F3"], 74.4, "circular")
        assert case.case_id == "INV-0001"
        assert case.status == CaseStatus.OBSERVED
        # circular is high-risk typology and 74.4 >= 65 -> CRITICAL
        assert case.priority == CasePriority.CRITICAL
        assert len(case.events) == 1
        assert case.events[0].event_type == "created"

    def test_create_case_high_score_starts_high_risk(self):
        cm = CaseManager()
        case = cm.create_case("CAND-002", ["F1", "F2", "F3"], 85.0, "circular")
        assert case.status == CaseStatus.HIGH_RISK

    def test_create_case_dedupes_by_ring(self):
        cm = CaseManager()
        c1 = cm.create_case("CAND-001", ["F1"], 60.0)
        c2 = cm.create_case("CAND-001", ["F1"], 60.0)
        assert c1.case_id == c2.case_id
        assert len(cm.list_cases()) == 1

    def test_get_case_by_ring(self):
        cm = CaseManager()
        cm.create_case("CAND-001", ["F1"], 60.0)
        case = cm.get_case_by_ring("CAND-001")
        assert case is not None
        assert case.ring_id == "CAND-001"

    def test_get_case_not_found(self):
        cm = CaseManager()
        assert cm.get_case("NOPE") is None

    def test_transition_valid(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        case = cm.transition(case.case_id, CaseStatus.SUSPICIOUS, actor="analyst1")
        assert case.status == CaseStatus.SUSPICIOUS
        assert len(case.events) == 2
        assert case.events[1].event_type == "status_change"
        assert case.events[1].from_status == CaseStatus.OBSERVED
        assert case.events[1].to_status == CaseStatus.SUSPICIOUS

    def test_transition_invalid_raises(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        with pytest.raises(ValueError):
            cm.transition(case.case_id, CaseStatus.CONFIRMED)

    def test_transition_terminal_state_raises(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        cm.transition(case.case_id, CaseStatus.SUSPICIOUS)
        cm.transition(case.case_id, CaseStatus.HIGH_RISK)
        cm.transition(case.case_id, CaseStatus.UNDER_REVIEW)
        cm.transition(case.case_id, CaseStatus.CONFIRMED)
        with pytest.raises(ValueError):
            cm.transition(case.case_id, CaseStatus.DISMISSED)

    def test_transition_nonexistent_case_raises(self):
        cm = CaseManager()
        with pytest.raises(KeyError):
            cm.transition("NOPE", CaseStatus.SUSPICIOUS)

    def test_full_lifecycle(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        cm.transition(case.case_id, CaseStatus.SUSPICIOUS)
        cm.transition(case.case_id, CaseStatus.HIGH_RISK)
        cm.transition(case.case_id, CaseStatus.UNDER_REVIEW)
        cm.transition(case.case_id, CaseStatus.CONFIRMED)
        assert case.status == CaseStatus.CONFIRMED
        assert len(case.events) == 5

    def test_add_note(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        event = cm.add_note(case.case_id, "Looks like a mule chain", actor="analyst1")
        assert event.event_type == "note_added"
        assert case.notes == ["Looks like a mule chain"]
        assert len(case.events) == 2

    def test_add_evidence(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        ev = {"type": "tx_ids", "ids": ["TX1", "TX2"]}
        event = cm.add_evidence(case.case_id, ev)
        assert event.event_type == "evidence_added"
        assert case.evidence == [ev]

    def test_assign(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        event = cm.assign(case.case_id, "analyst1")
        assert event.event_type == "assigned"
        assert case.assigned_to == "analyst1"

    def test_get_timeline(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1"], 60.0)
        cm.transition(case.case_id, CaseStatus.SUSPICIOUS)
        cm.add_note(case.case_id, "note")
        timeline = cm.get_timeline(case.case_id)
        assert len(timeline) == 3
        assert timeline[0]["event_type"] == "created"
        assert timeline[1]["event_type"] == "status_change"
        assert timeline[2]["event_type"] == "note_added"

    def test_list_cases_filter_by_status(self):
        cm = CaseManager()
        cm.create_case("CAND-001", ["F1"], 60.0)
        cm.create_case("CAND-002", ["F2"], 60.0)
        c3 = cm.create_case("CAND-003", ["F3"], 60.0)
        cm.transition(c3.case_id, CaseStatus.SUSPICIOUS)
        suspicious = cm.list_cases(status=CaseStatus.SUSPICIOUS)
        assert len(suspicious) == 1
        assert suspicious[0].ring_id == "CAND-003"

    def test_list_cases_filter_by_priority(self):
        cm = CaseManager()
        cm.create_case("CAND-001", ["F1"], 60.0)  # HIGH (score 60 < 65, but...)
        cm.create_case("CAND-002", ["F2"], 85.0)  # CRITICAL
        critical = cm.list_cases(priority=CasePriority.CRITICAL)
        assert len(critical) == 1
        assert critical[0].ring_id == "CAND-002"

    def test_summary(self):
        cm = CaseManager()
        cm.create_case("CAND-001", ["F1"], 60.0)
        cm.create_case("CAND-002", ["F2"], 60.0)
        s = cm.summary()
        assert s["total_cases"] == 2
        assert s["open_cases"] == 2
        assert s["closed_cases"] == 0

    def test_to_dict(self):
        cm = CaseManager()
        case = cm.create_case("CAND-001", ["F1", "F2"], 74.4, "circular")
        d = case.to_dict()
        assert d["case_id"] == "INV-0001"
        assert d["status"] == "OBSERVED"
        assert d["priority"] == "CRITICAL"
        assert d["members"] == ["F1", "F2"]
        assert d["score"] == 74.4
        assert d["typology"] == "circular"


# ---------------------------------------------------------------------------
# auto_create_cases tests
# ---------------------------------------------------------------------------

class TestAutoCreate:
    def _make_candidate(self, ring_id, score, typology=None, members=None):
        """Build a minimal RingCandidate-like object."""
        class FakeCandidate:
            def __init__(self):
                self.ring_id = ring_id
                self.score = score
                self.typology = typology
                self.typology_confidence = 0.9
                self.roles = []
                self.motifs = []
                self.sub_rings = []
                self.flow_summary = None
                self.members = members or [f"F{i}" for i in range(5)]
        return FakeCandidate()

    def test_auto_create_above_threshold(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 74.4, "circular")
        cases = auto_create_cases(cm, [cand], score_threshold=55.0)
        assert len(cases) == 1
        assert cases[0].ring_id == "CAND-001"

    def test_auto_create_below_threshold_skipped(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 50.0)
        cases = auto_create_cases(cm, [cand], score_threshold=55.0)
        assert cases == []

    def test_auto_create_dedupes(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 74.4)
        auto_create_cases(cm, [cand], score_threshold=55.0)
        cases = auto_create_cases(cm, [cand], score_threshold=55.0)
        assert len(cases) == 1
        assert len(cm.list_cases()) == 1

    def test_auto_create_attaches_motif_evidence(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 74.4)
        cand.motifs = [type("M", (), {"motif_type": "cycle", "evidence": "3-cycle"})()]
        cases = auto_create_cases(cm, [cand], score_threshold=55.0)
        assert len(cases[0].evidence) >= 1
        assert cases[0].evidence[0]["type"] == "detected_motifs"

    def test_auto_create_attaches_flow_evidence(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 74.4)
        cand.flow_summary = type("F", (), {
            "total_inflow": 1000, "total_outflow": 900,
            "flow_ratio": 1.1, "concentration": 0.8,
        })()
        cases = auto_create_cases(cm, [cand], score_threshold=55.0)
        assert any(e["type"] == "flow_summary" for e in cases[0].evidence)

    def test_auto_create_records_detector_version(self):
        cm = CaseManager()
        cand = self._make_candidate("CAND-001", 74.4)
        cases = auto_create_cases(cm, [cand], score_threshold=55.0, detector_version="det-abc")
        assert cases[0].detector_version == "det-abc"
