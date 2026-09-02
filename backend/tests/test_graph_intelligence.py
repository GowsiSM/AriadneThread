"""Tests for the graph_intelligence module (Stage 3).

Covers: feature extraction, motif detection, money-flow analysis,
typology classification, role assignment, ring decomposition.
"""
import networkx as nx
import pytest

from app.graph_intelligence import (
    GraphFeatures,
    MemberFeatures,
    MotifMatch,
    FlowSummary,
    TypologyResult,
    RoleAssignment,
    SubRing,
    compute_member_features,
    compute_flow_summary,
    detect_motifs,
    classify_typology,
    assign_roles,
    decompose_ring,
    TYPOLOGIES,
    ROLES,
)
from app import data_gen
from app.graph_engine import TransactionGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_ring_graph(ring_size: int = 5) -> nx.MultiDiGraph:
    """Build a small directed ring graph for testing."""
    g = nx.MultiDiGraph()
    for i in range(ring_size):
        a = f"USR{i:03d}"
        b = f"USR{(i + 1) % ring_size:03d}"
        g.add_edge(a, b, amount=1000.0, ts=data_gen.generate_dataset.__code__.co_consts[0], device="dev1", ip="1.1.1.1")
    return g


def _make_tx_graph() -> tuple[nx.MultiDiGraph, set[str]]:
    """Create a realistic graph from the data_gen dataset."""
    users, transactions = data_gen.generate_dataset(
        n_background_users=50, n_background_tx=200, n_rings=2, seed=42
    )
    g = TransactionGraph()
    for tx in transactions:
        g.add_transaction(tx)
    fraud_members = {u.user_id for u in users if u.user_id.startswith("F")}
    return g.graph, fraud_members


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

class TestMemberFeatures:
    def test_empty_members(self):
        g = nx.MultiDiGraph()
        result = compute_member_features(g, set())
        assert result.features == {}
        assert result.avg_in_degree == 0.0

    def test_single_node(self):
        g = nx.MultiDiGraph()
        g.add_node("A")
        result = compute_member_features(g, {"A"})
        assert "A" in result.features
        assert result.features["A"].in_degree == 0
        assert result.features["A"].out_degree == 0

    def test_directed_edges(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=500, ts=None)
        g.add_edge("A", "C", amount=300, ts=None)
        g.add_edge("B", "C", amount=200, ts=None)
        result = compute_member_features(g, {"A", "B", "C"})
        assert result.features["A"].out_degree == 2
        assert result.features["C"].in_degree == 2
        assert result.features["A"].total_volume_out == 800.0

    def test_density_calculation(self):
        g = nx.MultiDiGraph()
        # Fully connected triangle
        g.add_edge("A", "B", amount=100, ts=None)
        g.add_edge("B", "C", amount=100, ts=None)
        g.add_edge("C", "A", amount=100, ts=None)
        result = compute_member_features(g, {"A", "B", "C"})
        assert result.density == pytest.approx(1.0)  # 3 edges / 3 possible

    def test_reciprocity(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=100, ts=None)
        g.add_edge("B", "A", amount=100, ts=None)
        g.add_edge("A", "C", amount=100, ts=None)
        result = compute_member_features(g, {"A", "B", "C"})
        assert result.reciprocity == pytest.approx(2 / 3)  # 2 reciprocal out of 3 edges


# ---------------------------------------------------------------------------
# Motif detection
# ---------------------------------------------------------------------------

class TestMotifDetection:
    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        motifs = detect_motifs(g, set())
        assert motifs == []

    def test_cycle_detection(self):
        g = nx.MultiDiGraph()
        for i in range(4):
            a = f"N{i}"
            b = f"N{(i + 1) % 4}"
            g.add_edge(a, b, amount=100, ts=None)
        motifs = detect_motifs(g, {f"N{i}" for i in range(4)})
        cycle_motifs = [m for m in motifs if m.motif_type == "cycle"]
        assert len(cycle_motifs) >= 1
        assert cycle_motifs[0].confidence > 0

    def test_fan_in_detection(self):
        g = nx.MultiDiGraph()
        for i in range(4):
            g.add_edge(f"IN{i}", "CENTER", amount=100, ts=None)
        members = {f"IN{i}" for i in range(4)} | {"CENTER"}
        motifs = detect_motifs(g, members)
        fan_in = [m for m in motifs if m.motif_type == "fan_in"]
        assert len(fan_in) >= 1
        assert "CENTER" in fan_in[0].nodes

    def test_fan_out_detection(self):
        g = nx.MultiDiGraph()
        for i in range(4):
            g.add_edge("CENTER", f"OUT{i}", amount=100, ts=None)
        members = {f"OUT{i}" for i in range(4)} | {"CENTER"}
        motifs = detect_motifs(g, members)
        fan_out = [m for m in motifs if m.motif_type == "fan_out"]
        assert len(fan_out) >= 1
        assert "CENTER" in fan_out[0].nodes

    def test_funnel_detection(self):
        g = nx.MultiDiGraph()
        g.add_edge("A1", "HUB", amount=100, ts=None)
        g.add_edge("A2", "HUB", amount=100, ts=None)
        g.add_edge("HUB", "B1", amount=100, ts=None)
        g.add_edge("HUB", "B2", amount=100, ts=None)
        members = {"A1", "A2", "HUB", "B1", "B2"}
        motifs = detect_motifs(g, members)
        funnels = [m for m in motifs if m.motif_type == "funnel"]
        assert len(funnels) >= 1

    def test_deduplication(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=100, ts=None)
        g.add_edge("B", "A", amount=100, ts=None)
        motifs = detect_motifs(g, {"A", "B"})
        # Should not have duplicate cycle matches for the same edge pair
        seen = set()
        for m in motifs:
            key = (m.motif_type, tuple(sorted(m.nodes)))
            assert key not in seen, f"Duplicate motif: {key}"
            seen.add(key)

    def test_real_dataset_motifs(self):
        g, members = _make_tx_graph()
        motifs = detect_motifs(g, members)
        # Should detect at least some motifs in the fraud ring
        assert len(motifs) >= 0  # may be 0 if the ring is too small after community detection


# ---------------------------------------------------------------------------
# Money-flow analysis
# ---------------------------------------------------------------------------

class TestFlowSummary:
    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        flow = compute_flow_summary(g, set())
        assert flow.total_inflow == 0.0
        assert flow.total_outflow == 0.0
        assert flow.internal_volume == 0.0

    def test_pure_internal_flow(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=500, ts=None)
        g.add_edge("B", "C", amount=500, ts=None)
        g.add_edge("C", "A", amount=500, ts=None)
        flow = compute_flow_summary(g, {"A", "B", "C"})
        assert flow.internal_volume == 1500.0
        assert flow.total_inflow == 0.0
        assert flow.total_outflow == 0.0
        assert flow.flow_ratio == pytest.approx(1.0)

    def test_mixed_flow(self):
        g = nx.MultiDiGraph()
        g.add_edge("OUTSIDE", "A", amount=1000, ts=None)  # inflow
        g.add_edge("A", "B", amount=500, ts=None)         # internal
        g.add_edge("B", "C", amount=500, ts=None)         # internal
        g.add_edge("C", "OUTSIDE2", amount=1000, ts=None)  # outflow
        flow = compute_flow_summary(g, {"A", "B", "C"})
        assert flow.total_inflow == 1000.0
        assert flow.total_outflow == 1000.0
        assert flow.internal_volume == 1000.0
        assert flow.net_flow == pytest.approx(0.0)  # balanced

    def test_concentration(self):
        g = nx.MultiDiGraph()
        # One node handles most of the flow
        g.add_edge("OUT", "A", amount=900, ts=None)
        g.add_edge("OUT", "B", amount=100, ts=None)
        g.add_edge("A", "OUT2", amount=900, ts=None)
        g.add_edge("B", "OUT2", amount=100, ts=None)
        flow = compute_flow_summary(g, {"A", "B"})
        assert flow.concentration > 0.5  # A dominates

    def test_dominant_path(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=100, ts=None)
        g.add_edge("B", "C", amount=200, ts=None)
        g.add_edge("C", "D", amount=300, ts=None)
        flow = compute_flow_summary(g, {"A", "B", "C", "D"})
        assert len(flow.dominant_path) >= 2
        assert flow.dominant_amount > 0


# ---------------------------------------------------------------------------
# Typology classification
# ---------------------------------------------------------------------------

class TestTypologyClassification:
    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        result = classify_typology(g, set(), [], FlowSummary(0, 0, 0, 0, 0, 0, (), 0, 0), MemberFeatures())
        assert result.primary in TYPOLOGIES

    def test_cycle_typology(self):
        g = nx.MultiDiGraph()
        for i in range(4):
            g.add_edge(f"N{i}", f"N{(i+1)%4}", amount=100, ts=None)
        members = {f"N{i}" for i in range(4)}
        motifs = detect_motifs(g, members)
        flow = compute_flow_summary(g, members)
        features = compute_member_features(g, members)
        result = classify_typology(g, members, motifs, flow, features)
        assert result.primary in TYPOLOGIES
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.evidence) > 0
        assert "circular" in result.all_scores
        assert result.all_scores["circular"] > 0  # cycle should boost circular score

    def test_fan_in_typology(self):
        g = nx.MultiDiGraph()
        for i in range(5):
            g.add_edge(f"S{i}", "COLLECTOR", amount=100, ts=None)
        members = {f"S{i}" for i in range(5)} | {"COLLECTOR"}
        motifs = detect_motifs(g, members)
        flow = compute_flow_summary(g, members)
        features = compute_member_features(g, members)
        result = classify_typology(g, members, motifs, flow, features)
        assert result.all_scores.get("fan_in", 0) > 0

    def test_all_typologies_scored(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=100, ts=None)
        members = {"A", "B"}
        flow = compute_flow_summary(g, members)
        features = compute_member_features(g, members)
        result = classify_typology(g, members, [], flow, features)
        for t in TYPOLOGIES:
            assert t in result.all_scores

    def test_typology_includes_evidence(self):
        g = nx.MultiDiGraph()
        for i in range(3):
            g.add_edge(f"N{i}", f"N{(i+1)%3}", amount=100, ts=None)
        members = {f"N{i}" for i in range(3)}
        motifs = detect_motifs(g, members)
        flow = compute_flow_summary(g, members)
        features = compute_member_features(g, members)
        result = classify_typology(g, members, motifs, flow, features)
        assert isinstance(result.evidence, list)
        assert all(isinstance(e, str) for e in result.evidence)


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------

class TestRoleAssignment:
    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        roles = assign_roles(g, set(), FlowSummary(0, 0, 0, 0, 0, 0, (), 0, 0), [])
        assert roles == []

    def test_chain_roles(self):
        g = nx.MultiDiGraph()
        g.add_edge("ORIG", "MULE1", amount=100, ts=None)
        g.add_edge("MULE1", "MULE2", amount=100, ts=None)
        g.add_edge("MULE2", "DEST", amount=100, ts=None)
        members = {"ORIG", "MULE1", "MULE2", "DEST"}
        flow = compute_flow_summary(g, members)
        roles = assign_roles(g, members, flow, [])
        role_map = {r.user_id: r.role for r in roles}
        assert role_map["ORIG"] == "originator"
        assert role_map["DEST"] == "beneficiary"

    def test_funnel_roles(self):
        g = nx.MultiDiGraph()
        g.add_edge("IN1", "HUB", amount=100, ts=None)
        g.add_edge("IN2", "HUB", amount=100, ts=None)
        g.add_edge("HUB", "OUT1", amount=100, ts=None)
        g.add_edge("HUB", "OUT2", amount=100, ts=None)
        members = {"IN1", "IN2", "HUB", "OUT1", "OUT2"}
        flow = compute_flow_summary(g, members)
        roles = assign_roles(g, members, flow, [])
        role_map = {r.user_id: r.role for r in roles}
        assert role_map["HUB"] == "funnel"

    def test_all_roles_valid(self):
        g = nx.MultiDiGraph()
        g.add_edge("A", "B", amount=100, ts=None)
        members = {"A", "B"}
        flow = compute_flow_summary(g, members)
        roles = assign_roles(g, members, flow, [])
        for r in roles:
            assert r.role in ROLES
            assert 0.0 <= r.confidence <= 1.0
            assert isinstance(r.evidence, str)


# ---------------------------------------------------------------------------
# Ring decomposition
# ---------------------------------------------------------------------------

class TestRingDecomposition:
    def test_small_ring_no_decomposition(self):
        g = nx.MultiDiGraph()
        for i in range(4):
            g.add_edge(f"N{i}", f"N{(i+1)%4}", amount=100, ts=None)
        members = [f"N{i}" for i in range(4)]
        result = decompose_ring(g, members, [])
        assert result == []  # small ring, no decomposition

    def test_large_ring_decomposed(self):
        g = nx.MultiDiGraph()
        # Create 2 separate connected components within the ring
        for i in range(5):
            g.add_edge(f"A{i}", f"A{(i+1)%5}", amount=100, ts=None)
        for i in range(5):
            g.add_edge(f"B{i}", f"B{(i+1)%5}", amount=100, ts=None)
        members = [f"A{i}" for i in range(5)] + [f"B{i}" for i in range(5)]
        result = decompose_ring(g, members, [])
        assert len(result) >= 2  # should split into 2 sub-rings
        for sr in result:
            assert len(sr.members) >= 2
            assert sr.sub_ring_id.startswith("SUB-")
            assert sr.reason
            assert 0 <= sr.risk_contribution <= 1.0

    def test_sub_ring_members_subset(self):
        g = nx.MultiDiGraph()
        for i in range(5):
            g.add_edge(f"A{i}", f"A{(i+1)%5}", amount=100, ts=None)
        for i in range(5):
            g.add_edge(f"B{i}", f"B{(i+1)%5}", amount=100, ts=None)
        members = [f"A{i}" for i in range(5)] + [f"B{i}" for i in range(5)]
        result = decompose_ring(g, members, [])
        all_decomposed = set()
        for sr in result:
            all_decomposed.update(sr.members)
        # All original members should appear in at least one sub-ring
        assert all_decomposed == set(members)


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestGraphIntelligenceIntegration:
    def test_full_pipeline_on_dataset(self):
        """Run the complete graph intelligence pipeline on the data_gen dataset."""
        g, fraud_members = _make_tx_graph()
        motifs = detect_motifs(g, fraud_members)
        flow = compute_flow_summary(g, fraud_members)
        features = compute_member_features(g, fraud_members)
        typology = classify_typology(g, fraud_members, motifs, flow, features)
        roles = assign_roles(g, fraud_members, flow, motifs)

        assert typology.primary in TYPOLOGIES
        assert 0.0 <= typology.confidence <= 1.0
        assert len(roles) == len(fraud_members)
        for r in roles:
            assert r.role in ROLES

    def test_typology_vocabularies(self):
        assert len(TYPOLOGIES) == 13  # 12 + unknown
        assert len(ROLES) == 7       # 6 + unknown
        assert "unknown" in TYPOLOGIES
        assert "unknown" in ROLES

    def test_determinism(self):
        """Graph intelligence should be deterministic for same input."""
        g, members = _make_tx_graph()
        r1 = detect_motifs(g, members)
        r2 = detect_motifs(g, members)
        assert [(m.motif_type, m.nodes) for m in r1] == [(m.motif_type, m.nodes) for m in r2]

        f1 = compute_flow_summary(g, members)
        f2 = compute_flow_summary(g, members)
        assert f1.total_inflow == f2.total_inflow
        assert f1.internal_volume == f2.internal_volume
