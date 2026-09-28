from __future__ import annotations

from pathlib import Path
from typing import Any

from systemai.contracts.models import (
    ActionIntent,
    ActionTarget,
    RiskLevel,
    TaskRequest,
    VerificationSpec,
)
from systemai.planner.base import PlannedStep, Planner, TaskPlan


class RuleBasedPlanner(Planner):
    """Deterministic demo planner used for tests and offline bootstrapping.

    Syntax examples:
      write:/tmp/hello.txt::hello world
      mkdir:/tmp/example
      read:/tmp/hello.txt
    """

    async def plan(self, task_id: str, request: TaskRequest, context: dict[str, Any]) -> TaskPlan:
        goal = request.goal.strip()
        if goal.startswith("write:"):
            rest = goal[len("write:"):]
            path, content = rest.split("::", 1)
            path = str(Path(path).expanduser())
            action = ActionIntent(
                task_id=task_id,
                capability="file.write",
                target=ActionTarget(path=path),
                parameters={"content": content, "create_parents": True},
                expected_result=f"File {path} contains requested content",
                verification=[VerificationSpec(kind="file.content_equals", parameters={"path": path, "content": content})],
                risk=RiskLevel.MEDIUM,
            )
            steps = [PlannedStep(node_id="write_file", title="Write requested file", action=action)]
        elif goal.startswith("mkdir:"):
            path = str(Path(goal[len("mkdir:"):]).expanduser())
            action = ActionIntent(
                task_id=task_id,
                capability="directory.create",
                target=ActionTarget(path=path),
                expected_result=f"Directory {path} exists",
                verification=[VerificationSpec(kind="file.exists", parameters={"path": path})],
                risk=RiskLevel.LOW,
            )
            steps = [PlannedStep(node_id="create_directory", title="Create directory", action=action)]
        elif goal.startswith("read:"):
            path = str(Path(goal[len("read:"):]).expanduser())
            action = ActionIntent(
                task_id=task_id,
                capability="file.read",
                target=ActionTarget(path=path),
                expected_result=f"Read {path}",
                risk=RiskLevel.OBSERVE,
            )
            steps = [PlannedStep(node_id="read_file", title="Read file", action=action)]
        else:
            raise ValueError("RuleBasedPlanner supports write:, mkdir:, and read: demo goals. Inject StructuredPlanner for natural language.")
        return TaskPlan(task_id=task_id, summary=request.goal, steps=steps)
