from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: str
    label: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    relation: str
    target: str
    metadata: dict[str, Any]


class CapabilityGraph:
    """Small in-memory graph abstraction for applications, resources, skills and capabilities.

    Persistence can later move to SQLite/graph DB without changing planner-facing methods.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.out_edges: dict[str, list[GraphEdge]] = {}
        self.in_edges: dict[str, list[GraphEdge]] = {}

    def upsert_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def link(self, edge: GraphEdge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise KeyError("both edge endpoints must exist")
        self.out_edges.setdefault(edge.source, []).append(edge)
        self.in_edges.setdefault(edge.target, []).append(edge)

    def neighbors(self, node_id: str, relation: str | None = None) -> list[GraphNode]:
        edges = self.out_edges.get(node_id, [])
        if relation is not None:
            edges = [e for e in edges if e.relation == relation]
        return [self.nodes[e.target] for e in edges]

    def find(self, *, kind: str | None = None, label_contains: str | None = None) -> list[GraphNode]:
        result = list(self.nodes.values())
        if kind:
            result = [n for n in result if n.kind == kind]
        if label_contains:
            q = label_contains.lower()
            result = [n for n in result if q in n.label.lower()]
        return result
