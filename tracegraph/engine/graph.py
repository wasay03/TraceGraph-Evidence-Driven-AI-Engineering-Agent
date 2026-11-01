from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tracegraph.constants.graph import TIER_RANK
from tracegraph.engine.rpq import Label
from tracegraph.ontology import Registry


@dataclass(slots=True)
class NodeView:
    """
    #Feature: In-memory snapshot
    #Scenario: One node of a snapshot as the engine sees it
    #Complexity: Time O(1) - constant
    """

    id: int
    type: str
    key: str
    props: dict[str, Any]
    tier: str
    file: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(slots=True)
class EdgeView:
    """
    #Feature: In-memory snapshot
    #Scenario: One edge of a snapshot as the engine sees it
    #Complexity: Time O(1) - constant
    """

    id: int
    type: str
    src: int
    dst: int
    props: dict[str, Any]
    tier: str
    confidence: float | None = None

    @property
    def tier_rank(self) -> int:
        """
        #Feature: In-memory snapshot
        #Scenario: Rank of the edge tier (0 strongest)
        #Complexity: Time O(1) - constant
        """
        return TIER_RANK[self.tier]


@dataclass(slots=True)
class GraphSnapshot:
    """
    #Feature: In-memory snapshot (PRD 6, D4)
    #Scenario: Adjacency lists per edge type and direction for one (repo, seq), plus the coverage map
    #Complexity: Time O(n + e) to build, O(deg) per neighbour lookup
    """

    registry: Registry
    repo_id: int
    seq: int
    commit: str
    nodes: dict[int, NodeView] = field(default_factory=dict)
    edges: dict[int, EdgeView] = field(default_factory=dict)
    fwd: dict[str, dict[int, list[EdgeView]]] = field(default_factory=dict)
    rev: dict[str, dict[int, list[EdgeView]]] = field(default_factory=dict)
    holes: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    overlay_id: int | None = None

    def add_node(self, node: NodeView) -> None:
        """
        #Feature: In-memory snapshot
        #Scenario: Insert or replace a node
        #Complexity: Time O(1) - constant
        """
        self.nodes[node.id] = node

    def add_edge(self, edge: EdgeView) -> None:
        """
        #Feature: In-memory snapshot
        #Scenario: Index an edge forward and backward; edges with unknown endpoints are ignored
        #Complexity: Time O(1) - constant
        """
        if edge.src not in self.nodes or edge.dst not in self.nodes:
            return
        self.edges[edge.id] = edge
        self.fwd.setdefault(edge.type, {}).setdefault(edge.src, []).append(edge)
        self.rev.setdefault(edge.type, {}).setdefault(edge.dst, []).append(edge)

    def remove_edge(self, edge_id: int) -> None:
        """
        #Feature: In-memory snapshot
        #Scenario: Drop an edge from both indexes (overlays)
        #Complexity: Time O(deg) - degree of its endpoints
        """
        edge = self.edges.pop(edge_id, None)
        if edge is None:
            return
        self.fwd[edge.type][edge.src] = [e for e in self.fwd[edge.type][edge.src] if e.id != edge_id]
        self.rev[edge.type][edge.dst] = [e for e in self.rev[edge.type][edge.dst] if e.id != edge_id]

    def remove_node(self, node_id: int) -> None:
        """
        #Feature: In-memory snapshot
        #Scenario: Drop a node and every incident edge (overlays)
        #Complexity: Time O(deg) - degree of the node
        """
        incident = [e.id for index in (self.fwd, self.rev) for adj in index.values() for e in adj.get(node_id, [])]
        for edge_id in incident:
            self.remove_edge(edge_id)
        self.nodes.pop(node_id, None)

    def neighbors(self, node_id: int, label: Label, max_tier_rank: int) -> Iterator[tuple[int, EdgeView]]:
        """
        #Feature: In-memory snapshot
        #Scenario: Nodes one labelled hop away, honouring the query's minimum tier
        #Complexity: Time O(deg) - degree for that label
        """
        edge_type, direction = label
        index = self.fwd if direction == "fwd" else self.rev
        for edge in index.get(edge_type, {}).get(node_id, []):
            if edge.tier_rank <= max_tier_rank:
                yield (edge.dst if direction == "fwd" else edge.src), edge

    def degree(self, node_id: int, edge_types: list[str], direction: str) -> int:
        """
        #Feature: In-memory snapshot
        #Scenario: Fan-in or fan-out over a set of edge types (all types when empty)
        #Complexity: Time O(t) - number of edge types
        """
        index = self.fwd if direction == "fwd" else self.rev
        types = edge_types or list(index)
        return sum(len(index.get(t, {}).get(node_id, [])) for t in types)

    def of_type(self, type_name: str) -> list[NodeView]:
        """
        #Feature: In-memory snapshot
        #Scenario: Nodes of a type and its subtypes
        #Complexity: Time O(n) - scan of nodes
        """
        types = self.registry.subtypes(type_name)
        return [n for n in self.nodes.values() if n.type in types]

    def type_matches(self, node_id: int, type_names: list[str]) -> bool:
        """
        #Feature: In-memory snapshot
        #Scenario: Whether a node is an instance of any of the given types (empty means any)
        #Complexity: Time O(t * d) - types times depth
        """
        if not type_names:
            return True
        node = self.nodes.get(node_id)
        return node is not None and any(self.registry.is_subtype(node.type, t) for t in type_names)

    @classmethod
    def from_rows(cls, registry: Registry, repo_id: int, seq: int, commit: str, node_rows: list[dict],
                  edge_rows: list[dict], hole_rows: list[dict]) -> "GraphSnapshot":
        """
        #Feature: In-memory snapshot
        #Scenario: Build from tg_node_list_at / tg_edge_list_at / tg_coverage_hole_list rows
        #Complexity: Time O(n + e + h) - linear in rows
        """
        graph = cls(registry, repo_id, seq, commit)
        nodes_by_id, edges_by_id = registry.node_type_by_id, registry.edge_type_by_id
        for r in node_rows:
            graph.add_node(NodeView(r["id"], nodes_by_id[r["type_id"]].name, r["natural_key"], r["props"], r["tier"],
                                    r["file_path"], r["line_start"], r["line_end"]))
        for r in edge_rows:
            graph.add_edge(EdgeView(r["id"], edges_by_id[r["type_id"]].name, r["src"], r["dst"], r["props"], r["tier"],
                                    r["confidence"]))
        for h in hole_rows:
            if h["node_id"] is not None:
                graph.holes.setdefault(h["node_id"], []).append(h)
        return graph
