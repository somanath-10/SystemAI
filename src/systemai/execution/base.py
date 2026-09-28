from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from systemai.contracts.models import ActionIntent, ActionResult


class Executor(ABC):
    name: str

    @abstractmethod
    def supports(self, capability: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        raise NotImplementedError


class ExecutionGateway:
    """Routes validated actions to a concrete executor.

    Executors are replaceable adapters. SystemAI Core never depends directly on Cua,
    Playwright, or a platform-specific implementation.
    """

    def __init__(self, executors: Iterable[Executor] | None = None) -> None:
        self._executors: list[Executor] = list(executors or [])

    def register(self, executor: Executor) -> None:
        self._executors.append(executor)

    def resolve(self, capability: str) -> Executor:
        for executor in self._executors:
            if executor.supports(capability):
                return executor
        raise LookupError(f"no executor available for capability: {capability}")

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        executor = self.resolve(action.capability)
        return await executor.execute(action, capability_token=capability_token)
