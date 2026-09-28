from __future__ import annotations

import asyncio

import psutil

from systemai.contracts.models import SystemEvent
from systemai.monitoring.event_bus import EventBus


class ProcessMonitor:
    """Low-cost event collector; reasoning is invoked only for interesting events."""

    def __init__(self, bus: EventBus, interval_seconds: float = 2.0) -> None:
        self.bus = bus
        self.interval = interval_seconds
        self._running = False
        self._known: dict[int, str] = {}

    async def run(self) -> None:
        self._running = True
        self._known = self._snapshot()
        while self._running:
            await asyncio.sleep(self.interval)
            current = self._snapshot()
            for pid, name in current.items():
                if pid not in self._known:
                    await self.bus.publish(SystemEvent(event_type="PROCESS_STARTED", source="process_monitor", payload={"pid": pid, "name": name}))
            for pid, name in self._known.items():
                if pid not in current:
                    await self.bus.publish(SystemEvent(event_type="PROCESS_EXITED", source="process_monitor", payload={"pid": pid, "name": name}))
            self._known = current

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _snapshot() -> dict[int, str]:
        out: dict[int, str] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                out[int(proc.info["pid"])] = str(proc.info.get("name") or "")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out
