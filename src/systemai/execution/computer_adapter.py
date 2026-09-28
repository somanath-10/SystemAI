from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.execution.base import Executor


class ToolClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ComputerDriverExecutor(Executor):
    """Adapter boundary for Cua/Open-Computer-Use/MCP-style desktop drivers.

    We intentionally do not bind SystemAI Core to a moving third-party SDK. A thin
    ToolClient implementation can pin one audited version/commit and translate its
    tool names here.
    """

    name = "computer-driver"
    CAPABILITIES = {"ui.observe", "ui.click", "ui.set_value", "keyboard.hotkey", "screen.capture"}

    def __init__(self, client: ToolClient, mapping: dict[str, str] | None = None) -> None:
        self.client = client
        self.mapping = mapping or {
            "ui.observe": "get_app_state",
            "ui.click": "click",
            "ui.set_value": "set_value",
            "keyboard.hotkey": "press_key",
            "screen.capture": "screenshot",
        }

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        started = datetime.now(timezone.utc)
        tool = self.mapping[action.capability]
        args = dict(action.parameters)
        if action.target:
            args["target"] = action.target.model_dump(exclude_none=True)
        try:
            output = await self.client.call_tool(tool, args)
            effect = EffectStatus(output.get("effect", "unverifiable")) if output.get("effect") in {e.value for e in EffectStatus} else EffectStatus.UNVERIFIABLE
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.COMPLETED,
                effect=effect,
                executor=self.name,
                output=output,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.FAILED,
                effect=EffectStatus.FAILED,
                executor=self.name,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
