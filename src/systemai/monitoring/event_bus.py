from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable

from systemai.contracts.models import SystemEvent

EventHandler = Callable[[SystemEvent], Awaitable[None]]


class EventBus:
    """In-process event bus. Can later be swapped for NATS/Redis without agent changes."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._stream: asyncio.Queue[SystemEvent] = asyncio.Queue(maxsize=5000)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: SystemEvent) -> None:
        try:
            self._stream.put_nowait(event)
        except asyncio.QueueFull:
            _ = self._stream.get_nowait()
            self._stream.put_nowait(event)
        handlers = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)

    async def stream(self) -> AsyncIterator[SystemEvent]:
        while True:
            yield await self._stream.get()
