from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable

from systemai.contracts.models import ActionIntent, StepState


@dataclass(slots=True)
class TaskNode:
    node_id: str
    title: str
    action: ActionIntent
    dependencies: set[str] = field(default_factory=set)
    resource_requirements: set[str] = field(default_factory=set)
    state: StepState = StepState.PENDING
    attempts: int = 0
    max_attempts: int = 2
    last_error: str | None = None
    time_budget_seconds: int = 120
    cost_budget_usd: float = 0.0


class TaskGraphError(RuntimeError):
    pass


class TaskGraph:
    """Validated durable-compatible DAG of typed actions.

    The planner may propose graph changes, but this structure rejects missing
    dependencies and cycles before anything can become executable.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.nodes: dict[str, TaskNode] = {}
        self.children: dict[str, set[str]] = defaultdict(set)

    def add_node(self, node: TaskNode) -> None:
        if node.node_id in self.nodes:
            raise TaskGraphError(f"duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node
        for dep in node.dependencies:
            self.children[dep].add(node.node_id)
        try:
            self._validate_references()
            self._ensure_acyclic()
        except Exception:
            del self.nodes[node.node_id]
            for dep in node.dependencies:
                self.children[dep].discard(node.node_id)
            raise

    def add_dependency(self, node_id: str, dependency_id: str) -> None:
        self._require(node_id)
        self._require(dependency_id)
        self.nodes[node_id].dependencies.add(dependency_id)
        self.children[dependency_id].add(node_id)
        try:
            self._ensure_acyclic()
        except Exception:
            self.nodes[node_id].dependencies.remove(dependency_id)
            self.children[dependency_id].discard(node_id)
            raise

    def ready_nodes(self) -> list[TaskNode]:
        ready: list[TaskNode] = []
        for node in self.nodes.values():
            if node.state not in {StepState.PENDING, StepState.BLOCKED, StepState.READY}:
                continue
            if all(self.nodes[d].state in {StepState.SUCCEEDED, StepState.COMPLETED} for d in node.dependencies):
                node.state = StepState.READY
                ready.append(node)
            else:
                node.state = StepState.BLOCKED
        return ready

    def terminal(self) -> bool:
        return bool(self.nodes) and all(
            n.state in {StepState.SUCCEEDED, StepState.COMPLETED, StepState.FAILED, StepState.SKIPPED, StepState.CANCELLED}
            for n in self.nodes.values()
        )

    def successful(self) -> bool:
        return bool(self.nodes) and all(n.state in {StepState.SUCCEEDED, StepState.COMPLETED} for n in self.nodes.values())

    def failed_nodes(self) -> list[TaskNode]:
        return [n for n in self.nodes.values() if n.state == StepState.FAILED]

    def topological_order(self) -> list[str]:
        indegree = {node_id: len(node.dependencies) for node_id, node in self.nodes.items()}
        q = deque(sorted(k for k, v in indegree.items() if v == 0))
        out: list[str] = []
        while q:
            current = q.popleft()
            out.append(current)
            for child in sorted(self.children.get(current, set())):
                indegree[child] -= 1
                if indegree[child] == 0:
                    q.append(child)
        if len(out) != len(self.nodes):
            raise TaskGraphError("cycle detected")
        return out

    def dependencies_succeeded(self, node_id: str) -> bool:
        self._require(node_id)
        return all(self.nodes[d].state in {StepState.SUCCEEDED, StepState.COMPLETED} for d in self.nodes[node_id].dependencies)

    def descendants(self, node_id: str) -> set[str]:
        self._require(node_id)
        seen: set[str] = set()
        q: deque[str] = deque(self.children.get(node_id, set()))
        while q:
            child = q.popleft()
            if child in seen:
                continue
            seen.add(child)
            q.extend(self.children.get(child, set()))
        return seen

    def edges(self) -> list[tuple[str, str]]:
        return [(dep, node.node_id) for node in self.nodes.values() for dep in sorted(node.dependencies)]

    def _require(self, node_id: str) -> TaskNode:
        if node_id not in self.nodes:
            raise TaskGraphError(f"unknown node: {node_id}")
        return self.nodes[node_id]

    def _validate_references(self) -> None:
        missing = {dep for node in self.nodes.values() for dep in node.dependencies if dep not in self.nodes}
        if missing:
            raise TaskGraphError(f"missing dependency nodes: {sorted(missing)}")

    def _ensure_acyclic(self) -> None:
        self.topological_order()

    @classmethod
    def from_nodes(cls, task_id: str, nodes: Iterable[TaskNode]) -> "TaskGraph":
        graph = cls(task_id)
        pending = list(nodes)
        while pending:
            progressed = False
            for node in list(pending):
                if all(dep in graph.nodes for dep in node.dependencies):
                    graph.add_node(node)
                    pending.remove(node)
                    progressed = True
            if not progressed:
                unresolved = {n.node_id: sorted(n.dependencies) for n in pending}
                raise TaskGraphError(f"unresolvable dependencies: {unresolved}")
        return graph
