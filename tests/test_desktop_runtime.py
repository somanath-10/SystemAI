import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.contracts.desktop import DesktopDriverStatus, DesktopPermissionStatus
from systemai.contracts.models import ActionIntent
from systemai.runtime import build_runtime


class FakeDesktopClient:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    async def status(self) -> DesktopDriverStatus:
        return DesktopDriverStatus(configured=True, available=self.available, backend="fake")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        assert name == "list_apps"
        assert arguments == {}
        self.calls += 1
        return {"apps": [{"name": "TextEdit", "pid": 42, "bundle_id": "com.apple.TextEdit"}]}


class FakeWorkflowClient(FakeDesktopClient):
    def __init__(self, *, accessibility: bool = True) -> None:
        super().__init__()
        self.accessibility = accessibility
        self.value = "Before"
        self.tools: list[str] = []

    async def status(self) -> DesktopDriverStatus:
        return DesktopDriverStatus(configured=True, available=True, backend="fake", permissions=DesktopPermissionStatus(
            accessibility=self.accessibility, screen_recording=False,
        ))

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.tools.append(name)
        if name == "list_apps":
            return {"apps": [{"name": "TextEdit", "pid": 42, "bundle_id": "com.apple.TextEdit", "running": True}]}
        if name == "list_windows":
            return {"windows": [{"pid": 42, "window_id": 7, "title": "Untitled", "on_screen": True}]}
        if name == "get_window_state":
            return {"snapshot_id": "s1", "elements": [{"index": 1, "element_token": "s1:1", "role": "AXTextArea", "label": "Editor", "value": self.value}], "tree_markdown": self.value}
        if name == "launch_app":
            return {"effect": "confirmed", "pid": 42}
        if name == "set_value":
            self.value = arguments["value"]
            return {"effect": "confirmed", "value": self.value}
        if name == "click":
            return {"effect": "confirmed"}
        raise AssertionError(name)


@pytest.mark.asyncio
async def test_desktop_observation_is_authorized_and_independently_verified(tmp_path: Path) -> None:
    client = FakeDesktopClient()
    runtime = build_runtime(data_dir=tmp_path, desktop_client=client)
    executor = runtime.gateway.resolve("application.list")
    bare = ActionIntent(task_id="bare", capability="application.list", expected_result="apps")
    denied = await executor.execute(bare)
    assert denied.status.value == "rejected"
    assert client.calls == 0

    session = await runtime.create_desktop_observation()
    snapshot = session.snapshot()
    assert snapshot["state"] == "completed"
    assert snapshot["steps"][0]["verification"]["status"] == "passed"
    assert client.calls == 2  # execution, then a fresh verification observation
    assert runtime.store.verify_chain()


def test_desktop_api_fails_closed_without_driver(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, desktop_client=FakeDesktopClient(available=False)), base_url="http://127.0.0.1:8765")
    status = client.get("/desktop/status")
    assert status.status_code == 200
    assert status.json()["available"] is False
    run = client.post("/tasks/desktop-observation")
    assert run.status_code == 503
    assert client.app.state.runtime.sessions == {}


def test_desktop_api_returns_verified_observation(tmp_path: Path) -> None:
    fake = FakeDesktopClient()
    client = TestClient(create_app(tmp_path, desktop_client=fake), base_url="http://127.0.0.1:8765")
    assert client.get("/desktop/status").json()["available"] is True
    response = client.post("/tasks/desktop-observation")
    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert response.json()["steps"][0]["result"]["output"]["apps"][0]["name"] == "TextEdit"
    assert fake.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("control", "expected"), [("pause", "paused"), ("cancel", "cancelled"), ("take_control", "user_takeover")])
async def test_control_survives_in_flight_action(tmp_path: Path, control: str, expected: str) -> None:
    class BlockingDesktopClient(FakeDesktopClient):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def call_tool(self, name: str, arguments: dict) -> dict:
            if self.calls == 0:
                self.started.set()
                await self.release.wait()
            return await super().call_tool(name, arguments)

    fake = BlockingDesktopClient()
    runtime = build_runtime(data_dir=tmp_path, desktop_client=fake)
    task = asyncio.create_task(runtime.create_desktop_observation())
    await asyncio.wait_for(fake.started.wait(), 2)
    task_id = next(iter(runtime.sessions))
    getattr(runtime, control)(task_id)
    fake.release.set()
    session = await asyncio.wait_for(task, 2)
    assert session.state.value == expected
    assert session.snapshot()["steps"][0]["verification"]["status"] == "passed"


@pytest.mark.asyncio
async def test_desktop_verification_rejects_malformed_driver_observation(tmp_path: Path) -> None:
    class MalformedSecondObservation(FakeDesktopClient):
        async def call_tool(self, name: str, arguments: dict) -> dict:
            if self.calls == 1:
                self.calls += 1
                return {}
            return await super().call_tool(name, arguments)

    fake = MalformedSecondObservation()
    runtime = build_runtime(data_dir=tmp_path, desktop_client=fake)
    session = await runtime.create_desktop_observation()
    assert session.state.value == "failed"
    assert session.snapshot()["steps"][0]["verification"]["status"] == "failed"


@pytest.mark.asyncio
async def test_signed_desktop_launch_observe_write_and_click(tmp_path: Path) -> None:
    fake = FakeWorkflowClient()
    settings = Settings(_env_file=None, enable_desktop=True, enable_browser=False, desktop_allowed_apps="com.apple.TextEdit")
    runtime = build_runtime(data_dir=tmp_path, desktop_client=fake, settings=settings)
    launch = await runtime.create_desktop_task(capability="application.launch", bundle_id="com.apple.TextEdit")
    assert launch.state.value == "completed", launch.snapshot()
    observe = await runtime.create_desktop_task(capability="window.observe", bundle_id="com.apple.TextEdit", window_title="Untitled")
    assert observe.state.value == "completed", observe.snapshot()
    assert "tree_markdown" not in str(observe.snapshot())

    write = await runtime.create_desktop_task(
        capability="ui.set_value", bundle_id="com.apple.TextEdit", window_title="Untitled",
        element_name="Editor", element_role="AXTextArea", value="Private Test Text",
    )
    assert write.state.value == "waiting_for_approval"
    assert "Private Test Text" not in str(write.snapshot())
    action_id = next(iter(write.pending_approvals))
    runtime.approve(write.task_id, action_id, approved=True)
    await runtime.run(write.task_id)
    assert write.state.value == "completed", write.snapshot()
    assert fake.value == "Private Test Text"
    assert "Private Test Text" not in str(write.snapshot())
    assert "Private Test Text" not in str(runtime.store.list_events(task_id=write.task_id))

    click = await runtime.create_desktop_task(
        capability="ui.click", bundle_id="com.apple.TextEdit", window_title="Untitled",
        element_name="Editor", element_role="AXTextArea", verify_element_name="Editor",
    )
    assert click.state.value == "waiting_for_approval"
    action_id = next(iter(click.pending_approvals))
    runtime.approve(click.task_id, action_id, approved=True)
    await runtime.run(click.task_id)
    assert click.state.value == "completed", click.snapshot()
    assert "click" in fake.tools
    with pytest.raises(ValueError, match="allowlist"):
        await runtime.create_desktop_task(capability="application.launch", bundle_id="com.apple.Terminal")


@pytest.mark.asyncio
async def test_desktop_mutation_requires_accessibility(tmp_path: Path) -> None:
    fake = FakeWorkflowClient(accessibility=False)
    settings = Settings(_env_file=None, enable_desktop=True, enable_browser=False, desktop_allowed_apps="com.apple.TextEdit")
    runtime = build_runtime(data_dir=tmp_path, desktop_client=fake, settings=settings)
    with pytest.raises(RuntimeError, match="Accessibility"):
        await runtime.create_desktop_task(capability="ui.click", bundle_id="com.apple.TextEdit", window_title="Untitled", element_name="Editor", verify_element_name="Editor")
    assert fake.tools == []
