from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from systemai.contracts.models import ActionIntent, TaskRequest
from systemai.core.task_graph import TaskGraph, TaskNode


class PlannedStep(BaseModel):
    node_id: str
    title: str
    dependencies: list[str] = Field(default_factory=list)
    action: ActionIntent


class TaskPlan(BaseModel):
    task_id: str
    summary: str
    steps: list[PlannedStep]
    assumptions: list[str] = Field(default_factory=list)

    def to_graph(self) -> TaskGraph:
        return TaskGraph.from_nodes(
            self.task_id,
            [
                TaskNode(
                    node_id=s.node_id,
                    title=s.title,
                    dependencies=set(s.dependencies),
                    action=s.action,
                )
                for s in self.steps
            ],
        )


class Planner(ABC):
    @abstractmethod
    async def plan(self, task_id: str, request: TaskRequest, context: dict[str, Any]) -> TaskPlan:
        raise NotImplementedError
