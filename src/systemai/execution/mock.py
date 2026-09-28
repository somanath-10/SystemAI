from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.execution.base import Executor


class MockExecutor(Executor):
    name = "mock"

    def __init__(self, capabilities: set[str], handler: Callable[[ActionIntent], dict] | None = None) -> None:
        self.capabilities = capabilities
        self.handler = handler or (lambda action: {"echo": action.model_dump(mode="json")})

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        now = datetime.now(timezone.utc)
        return ActionResult(
            action_id=action.action_id,
            status=ActionStatus.COMPLETED,
            effect=EffectStatus.CONFIRMED,
            executor=self.name,
            output=self.handler(action),
            started_at=now,
            finished_at=datetime.now(timezone.utc),
        )
