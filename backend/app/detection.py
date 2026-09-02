"""
Deterministic ring-detection engine.

Everything in this module is plain graph algorithms + hand-written
heuristics -- no ML, no LLM. This is intentional: financial flagging
decisions must be reproducible and explainable, so the "decides" half of
the "AI proposes, code decides" split lives entirely here. See ai_explainer.py
for the (optional, non-authoritative) explanation layer.

Composite risk score (0-100) blends five signals:
  30% cycle involvement       -- closed loops of money (layering pattern)
  25% community isolation     -- dense internal ties, thin external ties
  20% PageRank anomaly        -- receiving disproportionate flow vs peers
  15% temporal burst          -- sudden fan-out shortly after a large inflow
  10% neighbor propagation    -- risk bleeds from already-flagged neighbors
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import statistics as stats

import networkx as nx

try:
    import community as community_louvain  # python-louvain
except ImportError:  # pragma: no cover
    community_louvain = None


@dataclass
class RingSignal:
    name: str
    weight: float
    value: float  # 0-1 normalized
    detail: str


@dataclass
class RingCandidate:
    ring_id: str
    members: list[str]
    score: float  # 0-100
    signals: list[RingSignal]
    formed_at: str | None = None
    key_edges: list[tuple[str, str]] = field(default_factory=list)


def _cycle_involvement(g: nx.MultiDiGraph, members: set[str]) -> tuple[float, str]:
    """Fraction of the community that sits on a directed cycle of length 3-8
    within the community's own induced subgraph."""
    if len(members) < 3:
        return 0.0, "too small for a cycle"
    sub = g.subgraph(members)
    simple = nx.DiGraph(sub)  # collapse multi-edges for cycle search
    on_cycle: set[str] = set()
    try:
        for cycle in nx.simple_cycles(simple, length_bound=8):
            if 3 <= len(cycle) <= 8:
                on_cycle.update(cycle)
    except Exception:
        pass
    frac = len(on_cycle) / len(members)
    detail = f"{len(on_cycle)}/{len(members)} members sit on a 3-8 hop money cycle"
    return frac, detail


def _community_isolation(g: nx.Graph, members: set[str]) -> tuple[float, str]:
    if not members:
        return 0.0, "empty"
    internal = 0
    external = 0
    for m in members:
        if m not in g:
            continue
        for nb in g.neighbors(m):
            if nb in members:
                internal += 1
            else:
                external += 1
    internal //= 2  # each internal edge counted twice
    total = internal + external
    if total == 0:
        return 0.0, "no edges"
    isolation = internal / total
    detail = f"{internal} internal vs {external} external edges (isolation={isolation:.2f})"
    return isolation, detail


def _pagerank_anomaly(g: nx.MultiDiGraph, members: set[str]) -> tuple[float, str]:
    if g.number_of_nodes() < 3:
        return 0.0, "graph too small"
    pr = nx.pagerank(nx.DiGraph(g), weight=None)
    values = list(pr.values())
    mean = stats.mean(values)
    stdev = stats.pstdev(values) or 1e-9
    member_scores = [pr.get(m, 0.0) for m in members if m in pr]
    if not member_scores:
        return 0.0, "no pagerank data"
    peak = max(member_scores)
    z = (peak - mean) / stdev
    norm = max(0.0, min(1.0, z / 4))  # z>=4 treated as maximal anomaly
    detail = f"peak PageRank z-score={z:.2f} vs network mean"
    return norm, detail


def _temporal_burst(g: nx.MultiDiGraph, members: set[str]) -> tuple[float, str]:
    """Detects a large inflow followed by fast fan-out to many members
    within a short window -- the classic mule-network signature."""
    edges = [
        (u, v, d) for u, v, d in g.edges(data=True) if u in members or v in members
    ]
    if len(edges) < 3:
        return 0.0, "not enough edges"
    edges.sort(key=lambda e: e[2]["ts"])
    window = timedelta(minutes=30)
    best_count = 0
    for i, (_, _, d0) in enumerate(edges):
        t0 = d0["ts"]
        cnt = sum(1 for _, _, d in edges if t0 <= d["ts"] <= t0 + window)
        best_count = max(best_count, cnt)
    norm = max(0.0, min(1.0, (best_count - 2) / 8))
    detail = f"up to {best_count} txns among members within a 30-min window"
    return norm, detail


def _neighbor_propagation(g: nx.Graph, members: set[str], already_flagged: set[str]) -> tuple[float, str]:
    if not already_flagged:
        return 0.0, "no prior flags this run"
    touch = 0
    for m in members:
        if m in g:
            for nb in g.neighbors(m):
                if nb in already_flagged:
                    touch += 1
                    break
    frac = touch / max(1, len(members))
    detail = f"{touch}/{len(members)} members border an already-flagged ring"
    return frac, detail


def detect_communities(shared_g: nx.Graph, tx_g_undirected: nx.Graph) -> list[set[str]]:
    """Union the shared-attribute graph and the transaction graph, then run
    Louvain community detection on the combination. Communities of size < 3
    are discarded as noise."""
    combined = nx.compose(shared_g, tx_g_undirected)
    if combined.number_of_nodes() == 0:
        return []
    if community_louvain is not None:
        partition = community_louvain.best_partition(combined, random_state=7)
    else:  # fallback: connected components if louvain isn't available
        partition = {}
        for i, comp in enumerate(nx.connected_components(combined)):
            for n in comp:
                partition[n] = i
    groups: dict[int, set[str]] = {}
    for node, comm_id in partition.items():
        groups.setdefault(comm_id, set()).add(node)
    return [members for members in groups.values() if len(members) >= 3]


def score_candidate(
    ring_index: int,
    members: set[str],
    directed_g: nx.MultiDiGraph,
    undirected_g: nx.Graph,
    already_flagged: set[str],
) -> RingCandidate:
    cyc_val, cyc_detail = _cycle_involvement(directed_g, members)
    iso_val, iso_detail = _community_isolation(undirected_g, members)
    pr_val, pr_detail = _pagerank_anomaly(directed_g, members)
    burst_val, burst_detail = _temporal_burst(directed_g, members)
    prop_val, prop_detail = _neighbor_propagation(undirected_g, members, already_flagged)

    signals = [
        RingSignal("cycle_involvement", 0.30, cyc_val, cyc_detail),
        RingSignal("community_isolation", 0.25, iso_val, iso_detail),
        RingSignal("pagerank_anomaly", 0.20, pr_val, pr_detail),
        RingSignal("temporal_burst", 0.15, burst_val, burst_detail),
        RingSignal("neighbor_propagation", 0.10, prop_val, prop_detail),
    ]
    score = sum(s.weight * s.value for s in signals) * 100
    key_edges = [
        (u, v) for u, v in undirected_g.edges(members) if u in members and v in members
    ][:15]
    return RingCandidate(
        ring_id=f"CAND-{ring_index:03d}",
        members=sorted(members),
        score=round(score, 1),
        signals=signals,
        key_edges=key_edges,
    )


def run_detection(
    directed_g: nx.MultiDiGraph,
    shared_attr_g: nx.Graph,
    score_threshold: float = 55.0,
) -> list[RingCandidate]:
    undirected_tx = nx.Graph()
    for u, v in directed_g.edges():
        undirected_tx.add_edge(u, v)

    communities = detect_communities(shared_attr_g, undirected_tx)
    already_flagged: set[str] = set()
    candidates: list[RingCandidate] = []
    for i, members in enumerate(communities):
        combined_view = nx.compose(shared_attr_g, undirected_tx)
        cand = score_candidate(i, members, directed_g, combined_view, already_flagged)
        candidates.append(cand)
        if cand.score >= score_threshold:
            already_flagged.update(members)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
