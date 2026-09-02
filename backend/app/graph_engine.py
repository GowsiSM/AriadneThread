"""
Incremental transaction graph.

Wraps a NetworkX DiGraph and exposes the small set of operations the
streaming pipeline needs: add a transaction as a weighted, timestamped edge,
and produce a bounded "recent window" view for detection so that the graph
does not grow unbounded in a long-running demo.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

import networkx as nx


class TransactionGraph:
    def __init__(self, window: timedelta = timedelta(hours=2)):
        self.graph = nx.MultiDiGraph()
        self.window = window
        self._recent_edges: deque = deque()  # (ts, sender, receiver, tx_id)
        self.edge_count = 0

    def add_transaction(self, tx) -> None:
        self.graph.add_node(tx.sender)
        self.graph.add_node(tx.receiver)
        self.graph.add_edge(
            tx.sender,
            tx.receiver,
            key=tx.tx_id,
            amount=tx.amount,
            ts=tx.ts,
            device=tx.sender_device,
            ip=tx.sender_ip,
        )
        self._recent_edges.append((tx.ts, tx.sender, tx.receiver, tx.tx_id))
        self.edge_count += 1
        self._evict_old(tx.ts)

    def _evict_old(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._recent_edges and self._recent_edges[0][0] < cutoff:
            self._recent_edges.popleft()

    def snapshot(self) -> nx.MultiDiGraph:
        """Return the live graph (callers must not mutate)."""
        return self.graph

    def projected_undirected(self) -> nx.Graph:
        """Collapse the directed multigraph into a simple undirected graph
        suitable for community detection, with edge weight = number of
        transactions between the pair (either direction)."""
        g = nx.Graph()
        for u, v, data in self.graph.edges(data=True):
            if g.has_edge(u, v):
                g[u][v]["weight"] += 1
                g[u][v]["amount_sum"] += data.get("amount", 0)
            else:
                g.add_edge(u, v, weight=1, amount_sum=data.get("amount", 0))
        return g

    def shared_attribute_graph(self, user_index: dict) -> nx.Graph:
        """User-user graph where an edge exists if two users share a device
        or IP (in addition to any direct transaction edge). This is what
        catches coordinated rings that don't transact with each other
        directly but clearly act together."""
        g = nx.Graph()
        by_device: dict[str, list[str]] = {}
        by_ip: dict[str, list[str]] = {}
        for uid, u in user_index.items():
            by_device.setdefault(u.device_id, []).append(uid)
            by_ip.setdefault(u.ip_address, []).append(uid)

        g.add_nodes_from(user_index.keys())
        for group in by_device.values():
            if 1 < len(group) <= 12:  # skip mega-shared devices as uninformative
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        g.add_edge(group[i], group[j], reason="device")
        for group in by_ip.values():
            if 1 < len(group) <= 12:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        if g.has_edge(group[i], group[j]):
                            g[group[i]][group[j]]["reason"] = "device+ip"
                        else:
                            g.add_edge(group[i], group[j], reason="ip")
        return g
