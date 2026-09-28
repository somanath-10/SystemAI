from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from systemai.contracts.models import GoalContract, ResourceScope
from systemai.core.task_graph import TaskGraph, TaskNode
from systemai.diagnostics import DeveloperDiagnosisEngineV1


class DeveloperDiagnosisPlannerV1:
    """Single-planner V1 implementation for the developer diagnosis wedge.

    It combines deterministic project inspection/diagnosis with typed remediation
    actions. A cloud/frontier planner can replace or augment this implementation
    behind the same TaskGraph contract later.
    """

    def __init__(self, diagnosis: DeveloperDiagnosisEngineV1 | None = None) -> None:
        self.diagnosis = diagnosis or DeveloperDiagnosisEngineV1()

    def goal_contract(self, goal: str, project_root: Path, *, actor_id: str = "local-user") -> GoalContract:
        root = project_root.expanduser().resolve(strict=True)
        return GoalContract(
            objective=goal,
            constraints=[
                "preserve user/project data",
                "keep mutations within the declared project scope unless explicitly approved",
                "do not disable security controls",
                "prefer the minimum-scope repair",
            ],
            success_conditions=[
                "configured project health condition is satisfied or the diagnosis reports a precise unresolved blocker",
                "all executed consequential actions are independently verified",
            ],
            forbidden_effects=[
                "delete unrelated files",
                "terminate unrelated processes",
                "change security settings without approval",
                "expose secret values in logs/model context",
            ],
            resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True)],
            actor_id=actor_id,
        )

    def plan(self, *, task_id: str, contract: GoalContract, project_root: Path) -> tuple[TaskGraph, object]:
        report = self.diagnosis.diagnose(task_id, project_root)
        graph = TaskGraph(task_id)
        previous: str | None = None
        for action in report.recommended_actions:
            if not action.node_id:
                action.node_id = f"node_{uuid4().hex[:12]}"
            dependencies = {previous} if previous else set()
            resources = set()
            for scope in action.resource_scope:
                if scope.kind == "filesystem":
                    resources.add(f"filesystem:{scope.value}")
                elif scope.kind == "port":
                    resources.add(f"port:{scope.value}")
                elif scope.kind == "process":
                    resources.add(f"process:{scope.value}")
                elif scope.kind == "database":
                    resources.add(f"database:{scope.value}")
                elif scope.kind == "network":
                    resources.add(f"network:{scope.value}")
            max_attempts = 5 if action.capability == "http.health" else 2
            node = TaskNode(
                node_id=action.node_id,
                title=action.expected_result,
                action=action,
                dependencies=dependencies,
                resource_requirements=resources,
                max_attempts=max_attempts,
            )
            graph.add_node(node)
            previous = action.node_id
        return graph, report
