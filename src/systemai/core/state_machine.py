from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from systemai.contracts.models import TaskState


_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.PLANNING, TaskState.CANCELLED},
    TaskState.PLANNING: {TaskState.READY, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.READY: {TaskState.EXECUTING, TaskState.WAITING_FOR_APPROVAL, TaskState.CANCELLED},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.EXECUTING: {
        TaskState.OBSERVING,
        TaskState.VERIFYING,
        TaskState.RECOVERING,
        TaskState.WAITING_FOR_APPROVAL,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.OBSERVING: {TaskState.EXECUTING, TaskState.VERIFYING, TaskState.FAILED},
    TaskState.VERIFYING: {TaskState.EXECUTING, TaskState.RECOVERING, TaskState.COMPLETED, TaskState.FAILED},
    TaskState.RECOVERING: {TaskState.EXECUTING, TaskState.WAITING_FOR_APPROVAL, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


class InvalidStateTransition(RuntimeError):
    pass


@dataclass(slots=True)
class Transition:
    from_state: TaskState
    to_state: TaskState
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStateMachine:
    """Explicit lifecycle state machine; the model cannot invent lifecycle states."""

    def __init__(self, initial: TaskState = TaskState.CREATED) -> None:
        self.state = initial
        self.history: list[Transition] = []

    def transition(self, target: TaskState, reason: str) -> None:
        if target == self.state:
            return
        if target not in _ALLOWED[self.state]:
            raise InvalidStateTransition(f"{self.state.value} -> {target.value} is not allowed")
        previous = self.state
        self.state = target
        self.history.append(Transition(previous, target, reason))
