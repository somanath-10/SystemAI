import pytest

from systemai.contracts.models import ActionIntent
from systemai.core.task_graph import TaskGraph, TaskGraphError, TaskNode


def action(task_id: str, cap: str = "file.read") -> ActionIntent:
    return ActionIntent(task_id=task_id, capability=cap, expected_result="ok")


def test_topological_order_and_cycle_rejection():
    g = TaskGraph("t")
    g.add_node(TaskNode("a", "A", action("t")))
    g.add_node(TaskNode("b", "B", action("t"), dependencies={"a"}))
    g.add_node(TaskNode("c", "C", action("t"), dependencies={"b"}))
    assert g.topological_order() == ["a", "b", "c"]
    with pytest.raises(TaskGraphError):
        g.add_dependency("a", "c")
