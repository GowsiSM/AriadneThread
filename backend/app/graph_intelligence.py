"""
Graph intelligence layer.

Pure graph algorithms that extract structural, flow, and typological
signals from the transaction graph.  Everything here is deterministic
and explainable — no ML, no LLM, no randomness (beyond what NetworkX
internals do, which is none for these algorithms).

Design principles:
  - Functions receive (directed_g, members, ...) and return dataclasses.
  - No side effects, no global state.
  - Each function is independently testable.
  - Integration with detection.py is optional — these can be called
    standalone for investigation / explanation.

Motif vocabulary (Section 28):
  cycle, fan_in, fan_out, chain, layering, funnel,
  shared_device, shared_ip, burst, pass_through, multi_hop

Ring role vocabulary (Section 33):
  originator, mule, intermediary, collector, funnel, beneficiary, unknown
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import networkx as nx


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraphFeatures:
    """Per-member graph features extracted from the directed transaction graph."""
    in_degree: int = 0
    out_degree: int = 0
    total_volume_in: float = 0.0
    total_volume_out: float = 0.0
    avg_txn_amount_in: float = 0.0
    avg_txn_amount_out: float = 0.0
    distinct_counterparties: int = 0
    clustering_coeff: float = 0.0
    betweenness_centrality: float = 0.0
    pagerank: float = 0.0


@dataclass
class MemberFeatures:
    """All per-member features for a ring candidate."""
    features: dict[str, GraphFeatures] = field(default_factory=dict)
    avg_in_degree: float = 0.0
    avg_out_degree: float = 0.0
    density: float = 0.0
    reciprocity: float = 0.0


def compute_member_features(
    g: nx.MultiDiGraph,
    members: set[str],
) -> MemberFeatures:
    """Compute per-member and aggregate graph features for a community."""
    if not members:
        return MemberFeatures()

    sub = g.subgraph(members)

    # Centrality metrics (computed on the full graph for context)
    undirected = nx.Graph(sub)
    bc = nx.betweenness_centrality(undirected) if len(undirected) >= 2 else {}
    pr = nx.pagerank(nx.DiGraph(sub), weight=None) if len(sub) >= 2 else {}

    features: dict[str, GraphFeatures] = {}
    for node in members:
        in_edges = list(sub.in_edges(node, data=True))
        out_edges = list(sub.out_edges(node, data=True))
        vol_in = sum(d.get("amount", 0) for _, _, d in in_edges)
        vol_out = sum(d.get("amount", 0) for _, _, d in out_edges)
        counterparties = set()
        for u, v, _ in in_edges:
            counterparties.add(u)
        for u, v, _ in out_edges:
            counterparties.add(v)
        features[node] = GraphFeatures(
            in_degree=len(in_edges),
            out_degree=len(out_edges),
            total_volume_in=vol_in,
            total_volume_out=vol_out,
            avg_txn_amount_in=vol_in / len(in_edges) if in_edges else 0.0,
            avg_txn_amount_out=vol_out / len(out_edges) if out_edges else 0.0,
            distinct_counterparties=len(counterparties),
            clustering_coeff=nx.clustering(undirected, node) if node in undirected else 0.0,
            betweenness_centrality=bc.get(node, 0.0),
            pagerank=pr.get(node, 0.0),
        )

    n = len(members)
    avg_in = sum(f.in_degree for f in features.values()) / n
    avg_out = sum(f.out_degree for f in features.values()) / n

    # Density: fraction of possible internal edges that exist
    possible = n * (n - 1) / 2 if n >= 2 else 1
    actual = undirected.number_of_edges()
    density = actual / possible

    # Reciprocity: fraction of directed edges that have a reverse edge
    directed_edges = sub.number_of_edges()
    reciprocal = 0
    for u, v in sub.edges():
        if sub.has_edge(v, u):
            reciprocal += 1
    reciprocity = reciprocal / directed_edges if directed_edges > 0 else 0.0

    return MemberFeatures(
        features=features,
        avg_in_degree=avg_in,
        avg_out_degree=avg_out,
        density=density,
        reciprocity=reciprocity,
    )


# ---------------------------------------------------------------------------
# Motif detection  (Section 28)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MotifMatch:
    """A single detected motif within a community."""
    motif_type: str          # cycle | fan_in | fan_out | chain | layering | funnel | ...
    nodes: tuple[str, ...]   # ordered nodes involved
    evidence: str = ""       # human-readable explanation
    confidence: float = 1.0  # 0-1


def detect_motifs(
    g: nx.MultiDiGraph,
    members: set[str],
    shared_g: nx.Graph | None = None,
) -> list[MotifMatch]:
    """Detect structural fraud motifs in the induced subgraph."""
    motifs: list[MotifMatch] = []
    if len(members) < 2:
        return motifs

    sub = g.subgraph(members)
    simple = nx.DiGraph(sub)  # collapse multi-edges

    # --- Cycles (length 3-8) ---
    try:
        for cycle in nx.simple_cycles(simple, length_bound=8):
            if 3 <= len(cycle) <= 8:
                motifs.append(MotifMatch(
                    motif_type="cycle",
                    nodes=tuple(cycle),
                    evidence=f"Directed cycle: {' → '.join(cycle)} → {cycle[0]}",
                    confidence=min(1.0, len(cycle) / 4),
                ))
    except Exception:
        pass

    # --- Fan-in (≥3 edges into one node) ---
    in_degrees = {n: simple.in_degree(n) for n in simple}
    for node, deg in in_degrees.items():
        if deg >= 3:
            predecessors = list(simple.predecessors(node))
            motifs.append(MotifMatch(
                motif_type="fan_in",
                nodes=tuple(predecessors + [node]),
                evidence=f"{deg} senders converge on {node}",
                confidence=min(1.0, deg / 5),
            ))

    # --- Fan-out (≥3 edges from one node) ---
    out_degrees = {n: simple.out_degree(n) for n in simple}
    for node, deg in out_degrees.items():
        if deg >= 3:
            successors = list(simple.successors(node))
            motifs.append(MotifMatch(
                motif_type="fan_out",
                nodes=tuple([node] + successors),
                evidence=f"{node} sends to {deg} receivers",
                confidence=min(1.0, deg / 5),
            ))

    # --- Chain (directed path of length ≥3) ---
    _detect_chains(simple, members, motifs)

    # --- Layering (chain with increasing amounts) ---
    _detect_layering(sub, motifs)

    # --- Funnel (fan-in → fan-out at same node) ---
    for node in simple:
        if simple.in_degree(node) >= 2 and simple.out_degree(node) >= 2:
            predecessors = list(simple.predecessors(node))
            successors = list(simple.successors(node))
            motifs.append(MotifMatch(
                motif_type="funnel",
                nodes=tuple(predecessors + [node] + successors),
                evidence=f"{node}: {len(predecessors)} in → {len(successors)} out",
                confidence=min(1.0, (simple.in_degree(node) + simple.out_degree(node)) / 8),
            ))

    # --- Shared device / IP (from shared_g) ---
    if shared_g is not None:
        _detect_shared_attribute_motifs(shared_g, members, motifs)

    # --- Deduplicate ---
    motifs = _deduplicate_motifs(motifs)
    return motifs


def _detect_chains(simple: nx.DiGraph, members: set[str], motifs: list[MotifMatch]) -> None:
    """Detect directed paths of length ≥3 (chain patterns)."""
    visited: set[tuple[str, ...]] = set()

    def _dfs(node: str, path: list[str]) -> None:
        if len(path) >= 4:  # path of 3+ edges
            key = tuple(path)
            if key not in visited:
                visited.add(key)
                motifs.append(MotifMatch(
                    motif_type="chain",
                    nodes=tuple(path),
                    evidence=f"Chain: {' → '.join(path)} ({len(path)-1} hops)",
                    confidence=min(1.0, (len(path) - 1) / 4),
                ))
        if len(path) >= 5:
            return
        for neighbor in simple.successors(node):
            if neighbor not in path:
                _dfs(neighbor, path + [neighbor])

    for start in members:
        if start not in simple:
            continue
        if simple.in_degree(start) == 0 or simple.out_degree(start) >= 2:
            _dfs(start, [start])


def _detect_layering(sub: nx.MultiDiGraph, motifs: list[MotifMatch]) -> None:
    """Detect layering: chain where amounts increase at each hop."""
    simple = nx.DiGraph(sub)
    for node in list(simple.nodes()):
        in_edges = list(sub.in_edges(node, data=True))
        out_edges = list(sub.out_edges(node, data=True))
        if in_edges and out_edges:
            avg_in = sum(d.get("amount", 0) for _, _, d in in_edges) / len(in_edges)
            avg_out = sum(d.get("amount", 0) for _, _, d in out_edges) / len(out_edges)
            if avg_out > avg_in * 1.3 and sub.out_degree(node) == 1:
                successor = list(simple.successors(node))
                predecessor = list(simple.predecessors(node))
                if successor:
                    motifs.append(MotifMatch(
                        motif_type="layering",
                        nodes=tuple(predecessor + [node] + successor),
                        evidence=f"Amount amplified at {node}: avg_in={avg_in:.0f} → avg_out={avg_out:.0f}",
                        confidence=min(1.0, (avg_out / avg_in - 1.0) / 2) if avg_in > 0 else 0.5,
                    ))


def _detect_shared_attribute_motifs(
    shared_g: nx.Graph,
    members: set[str],
    motifs: list[MotifMatch],
) -> None:
    """Detect shared-device and shared-IP motifs."""
    device_groups: dict[str, list[str]] = {}
    ip_groups: dict[str, list[str]] = {}
    for u in members:
        if u in shared_g:
            for nb in shared_g.neighbors(u):
                if nb in members and u < nb:
                    reason = shared_g[u][nb].get("reason", "")
                    if "device" in reason:
                        pair = tuple(sorted([u, nb]))
                        device_groups.setdefault("device", []).append(pair)
                    if "ip" in reason and "device" not in reason:
                        pair = tuple(sorted([u, nb]))
                        ip_groups.setdefault("ip", []).append(pair)

    if device_groups.get("device"):
        pairs = device_groups["device"]
        nodes = set()
        for a, b in pairs:
            nodes.update([a, b])
        if len(nodes) >= 3:
            motifs.append(MotifMatch(
                motif_type="shared_device",
                nodes=tuple(sorted(nodes)),
                evidence=f"{len(pairs)} pairs share devices among {len(nodes)} users",
                confidence=min(1.0, len(pairs) / 3),
            ))

    if ip_groups.get("ip"):
        pairs = ip_groups["ip"]
        nodes = set()
        for a, b in pairs:
            nodes.update([a, b])
        if len(nodes) >= 3:
            motifs.append(MotifMatch(
                motif_type="shared_ip",
                nodes=tuple(sorted(nodes)),
                evidence=f"{len(pairs)} pairs share IPs among {len(nodes)} users",
                confidence=min(1.0, len(pairs) / 3),
            ))


def _deduplicate_motifs(motifs: list[MotifMatch]) -> list[MotifMatch]:
    """Remove duplicate motif matches (same type + same node set)."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[MotifMatch] = []
    for m in motifs:
        key = (m.motif_type, tuple(sorted(m.nodes)))
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result


# ---------------------------------------------------------------------------
# Money-flow analysis  (Section 29)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlowSummary:
    """Aggregate money-flow metrics for a ring candidate."""
    total_inflow: float          # money entering the ring from outside
    total_outflow: float         # money leaving the ring to outside
    internal_volume: float       # money circulating inside the ring
    external_volume: float       # total money crossing ring boundary
    net_flow: float              # outflow - inflow (positive = ring is draining)
    flow_ratio: float            # internal / (internal + external)
    dominant_path: tuple[str, ...]  # highest-volume directed path
    dominant_amount: float       # volume on the dominant path
    concentration: float         # 0-1, how concentrated flow is (1 = one node handles all)


def compute_flow_summary(
    g: nx.MultiDiGraph,
    members: set[str],
) -> FlowSummary:
    """Analyze how money flows into, through, and out of a ring candidate."""
    members_set = set(members)
    inflow = 0.0
    outflow = 0.0
    internal = 0.0

    for u, v, d in g.edges(data=True):
        amt = d.get("amount", 0)
        if u in members_set and v in members_set:
            internal += amt
        elif u in members_set and v not in members_set:
            outflow += amt
        elif u not in members_set and v in members_set:
            inflow += amt

    external = inflow + outflow
    net_flow = outflow - inflow
    total = internal + external
    flow_ratio = internal / total if total > 0 else 0.0

    # Dominant path: longest weighted path through the ring
    dominant_path, dominant_amount = _find_dominant_path(g, members_set)

    # Concentration: what fraction of total flow passes through the busiest node
    node_volumes: dict[str, float] = {m: 0.0 for m in members}
    for u, v, d in g.edges(data=True):
        amt = d.get("amount", 0)
        if u in members_set:
            node_volumes[u] = node_volumes.get(u, 0) + amt
        if v in members_set:
            node_volumes[v] = node_volumes.get(v, 0) + amt
    total_node_vol = sum(node_volumes.values())
    max_node_vol = max(node_volumes.values()) if node_volumes else 0
    concentration = max_node_vol / total_node_vol if total_node_vol > 0 else 0.0

    return FlowSummary(
        total_inflow=inflow,
        total_outflow=outflow,
        internal_volume=internal,
        external_volume=external,
        net_flow=net_flow,
        flow_ratio=flow_ratio,
        dominant_path=dominant_path,
        dominant_amount=dominant_amount,
        concentration=concentration,
    )


def _find_dominant_path(
    g: nx.MultiDiGraph,
    members: set[str],
) -> tuple[tuple[str, ...], float]:
    """Find the highest-volume directed path within the member subgraph."""
    sub = g.subgraph(members)
    simple = nx.DiGraph(sub)

    # Aggregate amounts between pairs
    pair_amounts: dict[tuple[str, str], float] = {}
    for u, v, d in sub.edges(data=True):
        pair_amounts[(u, v)] = pair_amounts.get((u, v), 0) + d.get("amount", 0)

    best_path: tuple[str, ...] = ()
    best_amount = 0.0

    for source in members:
        if simple.in_degree(source) == 0:
            for target in members:
                if source != target and simple.out_degree(target) == 0:
                    try:
                        path = nx.shortest_path(simple, source, target)
                        path_amount = sum(
                            pair_amounts.get((path[i], path[i + 1]), 0)
                            for i in range(len(path) - 1)
                        )
                        if path_amount > best_amount:
                            best_amount = path_amount
                            best_path = tuple(path)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        pass

    # Fallback: highest-volume edge if no source→target path found
    if not best_path and pair_amounts:
        best_edge = max(pair_amounts, key=pair_amounts.get)
        best_path = best_edge
        best_amount = pair_amounts[best_edge]

    return best_path, best_amount


# ---------------------------------------------------------------------------
# Typology classification  (Sections 30-31)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TypologyResult:
    """Deterministic typology classification for a ring candidate."""
    primary: str           # most likely typology
    confidence: float      # 0-1
    evidence: list[str]    # supporting evidence strings
    all_scores: dict[str, float]  # score per typology


def classify_typology(
    g: nx.MultiDiGraph,
    members: set[str],
    motifs: list[MotifMatch],
    flow: FlowSummary,
    member_features: MemberFeatures,
) -> TypologyResult:
    """Classify the fraud typology based on graph patterns.

    Uses a deterministic scoring function — no ML, no randomness.
    Scores each of the 12 typologies and picks the highest.
    """
    scores: dict[str, float] = {t: 0.0 for t in TYPOLOGIES}
    evidence: list[str] = []

    # --- Structural signals from motifs ---
    motif_types = {m.motif_type for m in motifs}

    if "cycle" in motif_types:
        scores["circular"] += 0.4
        evidence.append("Directed cycle detected")

    if "fan_in" in motif_types:
        fan_in_count = sum(1 for m in motifs if m.motif_type == "fan_in")
        scores["fan_in"] += min(0.5, 0.2 * fan_in_count)
        evidence.append(f"{fan_in_count} fan-in pattern(s) detected")

    if "fan_out" in motif_types:
        fan_out_count = sum(1 for m in motifs if m.motif_type == "fan_out")
        scores["fan_out"] += min(0.5, 0.2 * fan_out_count)
        evidence.append(f"{fan_out_count} fan-out pattern(s) detected")

    if "funnel" in motif_types:
        scores["funnel"] += 0.5
        evidence.append("Funnel pattern (fan-in → fan-out) detected")

    if "layering" in motif_types:
        scores["layering"] += 0.5
        evidence.append("Layering pattern (amount amplification) detected")

    if "chain" in motif_types:
        chain_count = sum(1 for m in motifs if m.motif_type == "chain")
        if chain_count >= 2:
            scores["mule_chain"] += min(0.5, 0.15 * chain_count)
            evidence.append(f"{chain_count} chain patterns (mule chain)")

    if "shared_device" in motif_types:
        scores["shared_device"] += 0.5
        evidence.append("Shared device detected")

    if "shared_ip" in motif_types:
        scores["shared_ip"] += 0.5
        evidence.append("Shared IP detected")

    # --- Flow signals ---
    if flow.concentration > 0.6:
        scores["fan_in"] += 0.15
        scores["funnel"] += 0.10
        evidence.append(f"High flow concentration ({flow.concentration:.2f})")

    if flow.flow_ratio > 0.5:
        scores["pass_through"] += 0.2
        evidence.append(f"High internal flow ratio ({flow.flow_ratio:.2f})")

    if flow.total_inflow > 0 and flow.total_outflow > 0:
        ratio = flow.total_outflow / flow.total_inflow
        if 0.8 <= ratio <= 1.2:
            scores["pass_through"] += 0.15
            scores["layering"] += 0.1
            evidence.append(f"Inflow≈Outflow ratio={ratio:.2f} (pass-through)")

    # --- Degree signals ---
    n = len(members)
    if n >= 2:
        avg_out = member_features.avg_out_degree
        avg_in = member_features.avg_in_degree

        if avg_out > avg_in * 2:
            scores["fan_out"] += 0.15
            evidence.append(f"Avg out_degree ({avg_out:.1f}) >> in_degree ({avg_in:.1f})")
        elif avg_in > avg_out * 2:
            scores["fan_in"] += 0.15
            scores["smurfing"] += 0.1
            evidence.append(f"Avg in_degree ({avg_in:.1f}) >> out_degree ({avg_out:.1f})")

        if member_features.density > 0.6:
            scores["circular"] += 0.15
            evidence.append(f"High density ({member_features.density:.2f})")

        if member_features.reciprocity > 0.4:
            scores["circular"] += 0.1
            evidence.append(f"High reciprocity ({member_features.reciprocity:.2f})")

    # --- Temporal signals ---
    _classify_temporal(g, members, scores, evidence)

    # --- Multi-hop heuristic ---
    if n >= 5 and "chain" in motif_types:
        scores["multi_hop"] += 0.2
        evidence.append(f"Long chain ({n} members)")

    # --- Smurfing heuristic: many small, similar amounts ---
    _classify_smurfing(g, members, scores, evidence)

    # Pick winner
    primary = max(scores, key=scores.get)
    confidence = min(1.0, scores[primary])

    # Fallback to "unknown" if all scores are low
    if confidence < 0.1:
        primary = "unknown"
        confidence = 0.0
        evidence.append("No strong typology signal")

    return TypologyResult(
        primary=primary,
        confidence=confidence,
        evidence=evidence,
        all_scores=scores,
    )


def _classify_temporal(
    g: nx.MultiDiGraph,
    members: set[str],
    scores: dict[str, float],
    evidence: list[str],
) -> None:
    """Add temporal signals to typology scores."""
    edges = [
        (u, v, d) for u, v, d in g.edges(data=True)
        if (u in members or v in members) and d.get("ts") is not None
    ]
    if len(edges) < 3:
        return

    edges.sort(key=lambda e: e[2]["ts"])
    window = timedelta(minutes=30)

    # Count maximum burst within any 30-min window
    best_count = 0
    for i, (_, _, d0) in enumerate(edges):
        t0 = d0["ts"]
        cnt = sum(1 for _, _, d in edges if t0 <= d["ts"] <= t0 + window)
        best_count = max(best_count, cnt)

    if best_count >= 5:
        scores["burst"] += min(0.4, 0.08 * best_count)
        evidence.append(f"Burst: {best_count} txns in 30-min window")
    elif best_count >= 3:
        scores["burst"] += 0.15
        evidence.append(f"Mild burst: {best_count} txns in 30-min window")


def _classify_smurfing(
    g: nx.MultiDiGraph,
    members: set[str],
    scores: dict[str, float],
    evidence: list[str],
) -> None:
    """Detect smurfing: many small transactions below a threshold."""
    amounts = [
        d.get("amount", 0)
        for u, v, d in g.edges(data=True)
        if u in members and v in members
    ]
    if len(amounts) < 3:
        return

    median_amt = sorted(amounts)[len(amounts) // 2]
    small_count = sum(1 for a in amounts if a < median_amt * 0.5)
    if small_count >= 3 and small_count / len(amounts) > 0.5:
        scores["smurfing"] += min(0.3, 0.06 * small_count)
        evidence.append(f"Smurfing: {small_count}/{len(amounts)} txns below median×0.5")


# ---------------------------------------------------------------------------
# Role assignment  (Section 33)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoleAssignment:
    """Deterministic role assignment for a ring member."""
    user_id: str
    role: str            # originator | mule | intermediary | collector | funnel | beneficiary | unknown
    confidence: float    # 0-1
    evidence: str


def assign_roles(
    g: nx.MultiDiGraph,
    members: set[str],
    flow: FlowSummary,
    motifs: list[MotifMatch],
) -> list[RoleAssignment]:
    """Assign roles to each member of a ring candidate.

    Uses a deterministic heuristic based on:
      - In/out degree balance
      - Flow direction (sources vs sinks)
      - Position in chains/paths
      - Shared attribute connections
    """
    sub = g.subgraph(members)
    simple = nx.DiGraph(sub)

    assignments: list[RoleAssignment] = []

    for node in members:
        in_deg = simple.in_degree(node) if node in simple else 0
        out_deg = simple.out_degree(node) if node in simple else 0
        role, confidence, evidence = _classify_node_role(
            node, in_deg, out_deg, simple, sub, members, flow, motifs
        )
        assignments.append(RoleAssignment(
            user_id=node,
            role=role,
            confidence=confidence,
            evidence=evidence,
        ))

    return assignments


def _classify_node_role(
    node: str,
    in_deg: int,
    out_deg: int,
    simple: nx.DiGraph,
    sub: nx.MultiDiGraph,
    members: set[str],
    flow: FlowSummary,
    motifs: list[MotifMatch],
) -> tuple[str, float, str]:
    """Classify a single node's role. Returns (role, confidence, evidence)."""
    total = in_deg + out_deg
    if total == 0:
        return "unknown", 0.3, "No edges"

    # Source node: only outgoing edges within the ring
    if in_deg == 0 and out_deg >= 1:
        return "originator", 0.8, f"Source node: {out_deg} outgoing, 0 incoming"

    # Sink node: only incoming edges within the ring
    if out_deg == 0 and in_deg >= 1:
        return "beneficiary", 0.8, f"Sink node: {in_deg} incoming, 0 outgoing"

    # Funnel: significant both in and out
    if in_deg >= 2 and out_deg >= 2:
        return "funnel", 0.7, f"Hub: {in_deg} in, {out_deg} out"

    # Collector: mostly incoming with some forwarding
    if in_deg > out_deg * 2:
        return "collector", 0.65, f"Collector: {in_deg} in vs {out_deg} out"

    # Mule: passes money through (balanced in/out, or mostly out)
    if out_deg >= in_deg and out_deg >= 2:
        return "mule", 0.6, f"Mule: {out_deg} out, {in_deg} in"

    # Intermediary: moderate both directions
    if in_deg >= 1 and out_deg >= 1:
        return "intermediary", 0.5, f"Intermediary: {in_deg} in, {out_deg} out"

    return "unknown", 0.3, f"Unclear pattern: {in_deg} in, {out_deg} out"


# ---------------------------------------------------------------------------
# Ring decomposition  (Sections 34-35)
# ---------------------------------------------------------------------------

@dataclass
class SubRing:
    """A decomposed sub-component of a larger ring candidate."""
    sub_ring_id: str
    members: list[str]
    reason: str           # why this was split out
    risk_contribution: float  # estimated risk contribution (0-1)


def decompose_ring(
    g: nx.MultiDiGraph,
    members: list[str],
    motifs: list[MotifMatch],
) -> list[SubRing]:
    """Decompose a large ring into investigable sub-rings.

    A ring of 20+ members is hard to investigate. This splits it into
    focused groups of 3-8 members based on structural connectivity.

    Returns empty list if the ring is already small enough.
    """
    if len(members) <= 8:
        return []  # no decomposition needed

    member_set = set(members)
    sub = g.subgraph(member_set)
    simple = nx.DiGraph(sub)

    # Use weakly connected components on the induced subgraph
    # to find naturally separated groups
    components: list[set[str]] = []
    for comp in nx.weakly_connected_components(simple):
        if len(comp) >= 3:
            components.append(comp)

    if len(components) <= 1:
        # If no natural split, use the motif-based approach:
        # group members by their motif involvement
        components = _motif_based_split(members, motifs)

    sub_rings: list[SubRing] = []
    for i, comp in enumerate(components):
        if len(comp) < 2:
            continue
        # Estimate risk contribution based on edge density within component
        comp_sub = simple.subgraph(comp)
        possible = len(comp) * (len(comp) - 1) / 2 if len(comp) >= 2 else 1
        density = comp_sub.number_of_edges() / possible
        risk = min(1.0, density * 0.5 + len(comp) / 20)

        # Identify the split reason
        if any(m.motif_type == "cycle" and all(n in comp for n in m.nodes) for m in motifs):
            reason = "Isolated cycle substructure"
        elif any(m.motif_type == "fan_in" and m.nodes[-1] in comp for m in motifs):
            reason = "Fan-in cluster"
        elif any(m.motif_type == "fan_out" and m.nodes[0] in comp for m in motifs):
            reason = "Fan-out cluster"
        else:
            reason = f"Density-based split ({density:.2f})"

        sub_rings.append(SubRing(
            sub_ring_id=f"SUB-{i:03d}",
            members=sorted(comp),
            reason=reason,
            risk_contribution=risk,
        ))

    return sub_rings


def _motif_based_split(
    members: list[str],
    motifs: list[MotifMatch],
) -> list[set[str]]:
    """Split members based on which motifs they participate in."""
    groups: dict[int, set[str]] = {}
    unassigned = set(members)

    for i, motif in enumerate(motifs):
        if motif.motif_type in ("cycle", "fan_in", "fan_out", "funnel", "layering"):
            group = set(motif.nodes) & unassigned
            if len(group) >= 3:
                groups[i] = group
                unassigned -= group

    # Assign remaining members to the nearest group
    for node in list(unassigned):
        best_group = -1
        best_size = 0
        for gid, grp in groups.items():
            if len(grp) > best_size:
                best_group = gid
                best_size = len(grp)
        if best_group >= 0:
            groups[best_group].add(node)
        else:
            groups[len(groups)] = {node}

    return [grp for grp in groups.values() if len(grp) >= 2]


# ---------------------------------------------------------------------------
# Typology vocabulary
# ---------------------------------------------------------------------------

TYPOLOGIES = [
    "circular",
    "fan_in",
    "fan_out",
    "smurfing",
    "layering",
    "funnel",
    "mule_chain",
    "burst",
    "shared_device",
    "shared_ip",
    "pass_through",
    "multi_hop",
    "unknown",
]

# Role vocabulary
ROLES = [
    "originator",
    "mule",
    "intermediary",
    "collector",
    "funnel",
    "beneficiary",
    "unknown",
]
