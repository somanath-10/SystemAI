from pathlib import Path
import asyncio

import pytest
from conftest import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.contracts.models import SystemEvent
from systemai.runtime import build_runtime
from systemai.monitoring import EventBus, ProcessMonitor


@pytest.mark.asyncio
async def test_process_monitor_has_a_clean_runtime_lifecycle(tmp_path: Path) -> None:
    runtime = build_runtime(
        data_dir=tmp_path,
        settings=Settings(_env_file=None, enable_process_monitor=True, process_monitor_interval_seconds=60),
    )
    assert runtime.monitoring_status() == {"configured": True, "running": False}
    await runtime.start_monitoring()
    assert runtime.monitoring_status()["running"] is True
    await runtime.stop_monitoring()
    assert runtime.monitoring_status()["running"] is False


def test_monitor_rules_are_durable_and_deduplicate_alerts(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, enable_process_monitor=True, process_monitor_interval_seconds=60)
    client = TestClient(create_app(tmp_path, settings=settings), base_url="http://127.0.0.1:8765")
    rule = client.post("/monitor/rules", json={"event_type": "PROCESS_STARTED", "process_name": "Example", "cooldown_seconds": 60}).json()
    event = SystemEvent(event_type="PROCESS_STARTED", source="process_monitor", payload={"name": "Example", "pid": 42})
    bus = client.app.state.runtime.process_monitor.bus
    asyncio.run(bus.publish(event))
    asyncio.run(bus.publish(event))
    alerts = [item for item in client.get("/events").json()["items"] if item["event_type"] == "MonitorAlert"]
    assert len(alerts) == 1
    assert alerts[0]["payload"]["rule_id"] == rule["rule_id"]
    assert client.post(f"/monitor/rules/{rule['rule_id']}/state", json={"enabled": False}).status_code == 200
    assert client.app.state.runtime.store.verify_chain()

    client.app.state.runtime.close()
    restored = TestClient(create_app(tmp_path, settings=settings), base_url="http://127.0.0.1:8765")
    assert restored.get("/monitor/rules").json()["items"][0]["enabled"] is False


@pytest.mark.asyncio
async def test_process_monitor_detects_pid_reuse(monkeypatch) -> None:
    bus = EventBus()
    monitor = ProcessMonitor(bus, interval_seconds=0.01)
    snapshots = iter([{42: ("Old", 1.0)}, {42: ("New", 2.0)}])
    monkeypatch.setattr(monitor, "_snapshot", lambda: next(snapshots, {42: ("New", 2.0)}))
    events = []

    async def collect(event):
        events.append((event.event_type, event.payload["name"]))

    bus.subscribe("*", collect)
    task = asyncio.create_task(monitor.run())
    try:
        await asyncio.wait_for(_wait_for_events(events, 2), timeout=1)
    finally:
        monitor.stop()
        await task
    assert events == [("PROCESS_EXITED", "Old"), ("PROCESS_STARTED", "New")]


async def _wait_for_events(events, count: int) -> None:
    while len(events) < count:
        await asyncio.sleep(0.01)
