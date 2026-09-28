from __future__ import annotations

from typing import Any

import pytest

from systemai.contracts.desktop import DesktopDriverStatus, DesktopPermissionStatus
from systemai.contracts.models import ActionIntent, ActionTarget, VerificationSpec
from systemai.desktop import DesktopControlService
from systemai.execution.cua import CuaDesktopExecutor
from systemai.verification import DesktopVerificationProbe, Verifier


class FakeCuaClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.window_value = "Before"

    async def status(self):
        return DesktopDriverStatus(
            configured=True,
            available=True,
            backend="fake-cua",
            permissions=DesktopPermissionStatus(accessibility=True, screen_recording=True),
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "list_apps":
            return {"apps": [{"name": "TextEdit", "pid": 42, "bundle_id": "com.apple.TextEdit", "running": True}]}
        if name == "list_windows":
            return {"windows": [{"pid": 42, "window_id": 7, "title": "Untitled", "on_screen": True}]}
        if name == "get_window_state":
            return {
                "snapshot_id": "s002",
                "elements": [
                    {
                        "index": 3,
                        "element_token": "s002:3",
                        "role": "AXTextArea",
                        "label": "Editor",
                        "value": self.window_value,
                        "enabled": True,
                    }
                ],
                "tree_markdown": "# Editor",
                "degraded": False,
                "truncated": False,
            }
        if name == "click":
            return {"effect": "confirmed", "verified": True, "path": "ax"}
        if name == "set_value":
            self.window_value = arguments["value"]
            return {"effect": "confirmed", "verified": True, "path": "ax"}
        if name == "type_text":
            self.window_value = arguments["text"]
            return {"effect": "unverifiable", "verified": False, "path": "key_events"}
        if name == "hotkey":
            return {"effect": "unverifiable", "path": "key_events"}
        if name == "get_desktop_state":
            return {"screenshot_width": 1440, "screenshot_height": 900, "screenshot_png_b64": "AA=="}
        if name == "launch_app":
            return {"effect": "confirmed", "pid": 42, "windows": [{"window_id": 7, "title": "Untitled"}]}
        raise AssertionError(f"unexpected tool {name}: {arguments}")


@pytest.mark.asyncio
async def test_desktop_service_normalizes_apps_windows_and_snapshot():
    client = FakeCuaClient()
    desktop = DesktopControlService(client)

    apps = await desktop.list_apps()
    assert apps[0].bundle_id == "com.apple.TextEdit"
    windows = await desktop.list_windows(pid=42)
    assert windows[0].window_id == "7"
    snap = await desktop.snapshot_window(pid=42, window_id="7", include_screenshot=False)
    assert snap.snapshot_id == "s002"
    assert snap.elements[0].element_token == "s002:3"
    assert snap.elements[0].label == "Editor"


@pytest.mark.asyncio
async def test_cua_executor_uses_exact_window_and_fresh_element_token():
    client = FakeCuaClient()
    executor = CuaDesktopExecutor(client, session="task-session")
    action = ActionIntent(
        task_id="t1",
        capability="ui.click",
        target=ActionTarget(process_id=42, window_id="7", element_token="s002:3"),
        expected_result="Editor is clicked",
    )

    result = await executor.execute(action)
    assert result.effect.value == "confirmed"
    tool, args = client.calls[-1]
    assert tool == "click"
    assert args["target"] == {"kind": "window", "pid": 42, "window_id": 7}
    assert args["element_token"] == "s002:3"
    assert args["session"] == "task-session"
    assert args["delivery_mode"] == "background"


@pytest.mark.asyncio
async def test_cua_executor_rejects_bare_element_index():
    client = FakeCuaClient()
    executor = CuaDesktopExecutor(client)
    action = ActionIntent(
        task_id="t1",
        capability="ui.click",
        target=ActionTarget(process_id=42, window_id="7"),
        parameters={"element_index": 3},
        expected_result="Editor is clicked",
    )
    result = await executor.execute(action)
    assert result.status.value == "failed"
    assert "snapshot_id" in (result.error or "")
    assert client.calls == []


@pytest.mark.asyncio
async def test_desktop_verifier_takes_fresh_snapshot_for_value_check():
    client = FakeCuaClient()
    desktop = DesktopControlService(client)
    verifier = Verifier(DesktopVerificationProbe(desktop))
    executor = CuaDesktopExecutor(client)

    action = ActionIntent(
        task_id="t1",
        capability="ui.set_value",
        target=ActionTarget(process_id=42, window_id="7", element_token="s001:3"),
        parameters={"value": "After"},
        expected_result="Editor contains After",
        verification=[
            VerificationSpec(
                kind="ui.element_value_equals",
                parameters={"pid": 42, "window_id": "7", "label": "Editor", "role": "AXTextArea", "value": "After"},
            )
        ],
    )
    result = await executor.execute(action)
    verification = await verifier.verify(action, result)
    assert verification.status.value == "passed"
    assert client.calls[-1][0] == "get_window_state"


@pytest.mark.asyncio
async def test_keyboard_type_never_mixes_token_and_pixel_targeting():
    client = FakeCuaClient()
    executor = CuaDesktopExecutor(client)
    action = ActionIntent(
        task_id="t1",
        capability="keyboard.type",
        target=ActionTarget(process_id=42, window_id="7", element_token="s002:3"),
        parameters={"text": "hello", "x": 10, "y": 20},
        expected_result="Text is entered",
    )
    result = await executor.execute(action)
    assert result.status.value == "failed"
    assert "cannot mix" in (result.error or "")

@pytest.mark.asyncio
async def test_semantic_selector_resolves_app_window_and_fresh_token_before_action():
    client = FakeCuaClient()
    executor = CuaDesktopExecutor(client, session="semantic")
    action = ActionIntent(
        task_id="t1",
        capability="ui.click",
        target=ActionTarget(
            bundle_id="com.apple.TextEdit",
            window_title="Untitled",
            element_name="Editor",
            element_role="AXTextArea",
        ),
        expected_result="Editor is clicked",
    )

    result = await executor.execute(action)
    assert result.status.value == "completed"
    assert [name for name, _ in client.calls[-4:]] == [
        "list_apps",
        "list_windows",
        "get_window_state",
        "click",
    ]
    click_args = client.calls[-1][1]
    assert click_args["target"] == {"kind": "window", "pid": 42, "window_id": 7}
    assert click_args["element_token"] == "s002:3"

@pytest.mark.asyncio
async def test_runtime_completes_semantic_desktop_dag_without_dynamic_ids(tmp_path):
    import asyncio

    from systemai.contracts.models import RiskLevel, TaskRequest
    from systemai.core.capabilities import default_capabilities
    from systemai.core.runtime import SystemAIRuntime
    from systemai.execution import ExecutionGateway
    from systemai.memory import AuditLedger, MemoryStore
    from systemai.monitoring import EventBus
    from systemai.planner.base import PlannedStep, Planner, TaskPlan
    from systemai.recovery import RecoveryEngine
    from systemai.security import CapabilityTokenService, PolicyKernel

    class PlannerImpl(Planner):
        async def plan(self, task_id, request, context):
            launch = ActionIntent(
                task_id=task_id,
                capability="application.launch",
                target=ActionTarget(bundle_id="com.apple.TextEdit", application="TextEdit"),
                expected_result="TextEdit is running",
                verification=[VerificationSpec(kind="application.running", parameters={"bundle_id": "com.apple.TextEdit"})],
                risk=RiskLevel.LOW,
            )
            write = ActionIntent(
                task_id=task_id,
                capability="ui.set_value",
                target=ActionTarget(
                    bundle_id="com.apple.TextEdit",
                    window_title="Untitled",
                    element_name="Editor",
                    element_role="AXTextArea",
                ),
                parameters={"value": "SystemAI V0.2"},
                expected_result="Editor contains SystemAI V0.2",
                verification=[
                    VerificationSpec(
                        kind="ui.element_value_equals",
                        parameters={
                            "bundle_id": "com.apple.TextEdit",
                            "window_title": "Untitled",
                            "element_name": "Editor",
                            "element_role": "AXTextArea",
                            "value": "SystemAI V0.2",
                        },
                    )
                ],
                risk=RiskLevel.MEDIUM,
            )
            return TaskPlan(
                task_id=task_id,
                summary=request.goal,
                steps=[
                    PlannedStep(node_id="launch", title="Launch TextEdit", action=launch),
                    PlannedStep(node_id="write", title="Write text", dependencies=["launch"], action=write),
                ],
            )

    client = FakeCuaClient()
    desktop = DesktopControlService(client, session="runtime")
    runtime = SystemAIRuntime(
        planner=PlannerImpl(),
        policy=PolicyKernel(default_capabilities()),
        gateway=ExecutionGateway([CuaDesktopExecutor(client, session="runtime")]),
        verifier=Verifier(DesktopVerificationProbe(desktop)),
        recovery=RecoveryEngine(),
        memory=MemoryStore(tmp_path / "memory.db"),
        audit=AuditLedger(tmp_path / "audit.db"),
        event_bus=EventBus(),
        token_service=CapabilityTokenService(b"x" * 32),
        allowed_roots=[tmp_path],
    )
    session = await runtime.create_task(TaskRequest(goal="Write SystemAI V0.2 in TextEdit"))
    for _ in range(100):
        snap = runtime.get_snapshot(session.task_id)
        if snap["state"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.01)
    snap = runtime.get_snapshot(session.task_id)
    assert snap["state"] == "completed"
    assert client.window_value == "SystemAI V0.2"
