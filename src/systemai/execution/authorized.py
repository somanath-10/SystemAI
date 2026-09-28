from __future__ import annotations

from abc import abstractmethod

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.execution.base import Executor
from systemai.orchestration.event_store import EventStore
from systemai.security.signing import CapabilityVerifier


class AuthorizedExecutor(Executor):
    """Executor base that requires a signed, single-use capability token."""

    def __init__(self, *, name: str, verifier: CapabilityVerifier, event_store: EventStore | None = None) -> None:
        self.name = name
        self.verifier = verifier
        self.event_store = event_store

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        if not capability_token:
            return ActionResult(action_id=action.action_id, status="rejected", effect="failed", executor=self.name, error="missing capability token")
        try:
            claims = self.verifier.verify(capability_token, action=action, consume=True)
            if self.event_store and not self.event_store.mark_nonce_used(claims.nonce, action.action_id):
                raise ValueError("capability token nonce already consumed")
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="rejected", effect="failed", executor=self.name, error=f"authorization failed: {exc}")
        return await self.execute_authorized(action)

    @abstractmethod
    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        raise NotImplementedError
