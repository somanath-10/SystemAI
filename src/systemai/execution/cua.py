from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.desktop import DesktopControlService
from systemai.execution.base import Executor
from systemai.execution.cua_cli import CuaDriverError


class CuaDesktopExecutor(Executor):
    """SystemAI ActionIntent -> Cua Driver semantic desktop contract.

    Important properties:
    - exact app/window resolution before acting;
    - fresh accessibility snapshot before semantic element actions;
    - element tokens preferred over indexes/coordinates;
    - ambiguous selectors fail closed;
    - no model-generated code is evaluated or executed.
    """

    name = "cua"
    CAPABILITIES = {
        "application.list",
        "application.launch",
        "window.list",
        "window.observe",
        "window.activate",
        "ui.observe",
        "ui.click",
        "ui.set_value",
        "ui.scroll",
        "ui.drag",
        "keyboard.hotkey",
        "keyboard.type",
        "screen.capture",
    }

    def __init__(self, client: Any, *, session: str = "systemai") -> None:
        self.client = client
        self.session = session
        self.desktop = DesktopControlService(client, session=session)

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        started = datetime.now(timezone.utc)
        try:
            tool, args = await self._translate(action)
            output = await self.client.call_tool(tool, args)
            effect = _effect(output)
            if effect == EffectStatus.UNVERIFIABLE and action.capability in {
                "application.list", "window.list", "window.observe", "ui.observe", "screen.capture"
            }:
                effect = EffectStatus.CONFIRMED
            warnings: list[str] = []
            if output.get("degraded"):
                warnings.append(str(output.get("degraded_reason") or "desktop driver returned a degraded result"))
            if output.get("truncated"):
                warnings.append("desktop snapshot was truncated; do not infer uniqueness outside the returned projection")
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.COMPLETED,
                effect=effect,
                executor=self.name,
                output=output,
                warnings=warnings,
                fallback_used=_fallback(output),
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
        except CuaDriverError as exc:
            output = {"driver_error_code": exc.code, "driver_payload": exc.payload}
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.FAILED,
                effect=EffectStatus.FAILED,
                executor=self.name,
                output=output,
                error=f"CuaDriverError[{exc.code or 'unknown'}]: {exc}",
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

    async def _translate(self, action: ActionIntent) -> tuple[str, dict[str, Any]]:
        cap = action.capability
        params = dict(action.parameters)
        target = action.target

        if cap == "application.list":
            return "list_apps", {}

        if cap == "application.launch":
            bundle_id = params.pop("bundle_id", None) or (target.bundle_id if target else None)
            app = params.pop("application", None) or (target.application if target else None)
            if not bundle_id and not app:
                raise ValueError("application.launch requires target.bundle_id or target.application")
            args = dict(params)
            if bundle_id:
                args["bundle_id"] = bundle_id
            else:
                args["application"] = app
            return "launch_app", args

        if cap == "window.list":
            pid = params.pop("pid", None) or (target.process_id if target else None)
            if pid is None and target and (target.bundle_id or target.application):
                app = await self._resolve_application(target)
                pid = app.pid
            args = dict(params)
            if pid is not None:
                args["pid"] = int(pid)
            args.setdefault("on_screen_only", True)
            return "list_windows", args

        if cap in {"window.observe", "ui.observe"}:
            if target and self._has_window_selector(target):
                return "get_window_state", await self._window_observe_args(action)
            if cap == "window.observe":
                raise ValueError("window.observe requires an exact or resolvable application/window target")
            return "get_desktop_state", self._desktop_observe_args(action)

        if cap == "screen.capture":
            if target and self._has_window_selector(target):
                args = await self._window_observe_args(action)
                args["include_screenshot"] = True
                return "get_window_state", args
            return "get_desktop_state", self._desktop_observe_args(action)

        if cap == "window.activate":
            pid, window_id = await self._resolve_window(action)
            clean = {k: v for k, v in params.items() if k not in {"pid", "window_id"}}
            return "bring_to_front", {"pid": pid, "window_id": window_id, **clean}

        if cap == "ui.click":
            args = await self._action_args(action)
            await self._add_element_or_point(args, action, require_target=True)
            return "click", args

        if cap == "ui.set_value":
            args = await self._action_args(action)
            await self._add_semantic_element(args, action)
            if "value" not in params:
                raise ValueError("ui.set_value requires parameters.value")
            args["value"] = params["value"]
            return "set_value", args

        if cap == "ui.scroll":
            args = await self._action_args(action)
            direction = params.get("direction")
            if not direction:
                raise ValueError("ui.scroll requires parameters.direction")
            args["direction"] = direction
            for key in ("amount", "pages", "delta_x", "delta_y"):
                if key in params:
                    args[key] = params[key]
            if target and (target.element_token or target.element_name or target.element_role):
                await self._add_semantic_element(args, action)
            return "scroll", args

        if cap == "ui.drag":
            args = await self._action_args(action)
            for key in ("from_x", "from_y", "to_x", "to_y"):
                if key not in params:
                    raise ValueError(f"ui.drag requires parameters.{key}")
                args[key] = params[key]
            return "drag", args

        if cap == "keyboard.hotkey":
            args = await self._action_args(action)
            keys = params.get("keys")
            if isinstance(keys, str):
                keys = [part.strip().lower() for part in keys.replace("+", " ").split() if part.strip()]
            if not isinstance(keys, list) or not keys:
                raise ValueError("keyboard.hotkey requires parameters.keys")
            args["keys"] = keys
            return "hotkey", args

        if cap == "keyboard.type":
            args = await self._action_args(action)
            if "text" not in params:
                raise ValueError("keyboard.type requires parameters.text")
            args["text"] = str(params["text"])
            token = params.get("element_token") or (target.element_token if target else None)
            x, y = params.get("x"), params.get("y")
            semantic_selector = bool(target and (target.element_name or target.element_role))
            if (token or semantic_selector) and (x is not None or y is not None):
                raise ValueError("keyboard.type cannot mix semantic element targeting and coordinates")
            if token or semantic_selector:
                await self._add_semantic_element(args, action)
            elif x is not None or y is not None:
                if x is None or y is None:
                    raise ValueError("keyboard.type coordinate mode requires both x and y")
                args["x"], args["y"] = x, y
            return "type_text", args

        raise NotImplementedError(cap)

    async def _window_observe_args(self, action: ActionIntent) -> dict[str, Any]:
        pid, window_id = await self._resolve_window(action)
        args = dict(action.parameters)
        args["pid"] = pid
        args["window_id"] = window_id
        args.setdefault("include_accessibility_tree", True)
        args.setdefault("include_screenshot", True)
        args.setdefault("session", self.session)
        return args

    def _desktop_observe_args(self, action: ActionIntent) -> dict[str, Any]:
        params = dict(action.parameters)
        params.pop("target", None)
        params.pop("display_id", None)
        params.setdefault("session", self.session)
        return params

    async def _action_args(self, action: ActionIntent) -> dict[str, Any]:
        params = {
            k: v
            for k, v in action.parameters.items()
            if k not in {
                "element_token", "element_index", "snapshot_id", "x", "y",
                "pid", "window_id", "value", "text", "keys",
                "from_x", "from_y", "to_x", "to_y", "direction",
            }
        }
        target = action.target
        if target and self._has_window_selector(target):
            pid, window_id = await self._resolve_window(action)
            params["target"] = {"kind": "window", "pid": pid, "window_id": window_id}
        elif target and target.display_id:
            params["target"] = {"kind": "desktop", "display_id": target.display_id}
        elif "target" not in params:
            raise ValueError("desktop action requires an exact or resolvable window/desktop target")
        params.setdefault("delivery_mode", "background")
        params.setdefault("session", self.session)
        return params

    async def _add_element_or_point(self, args: dict[str, Any], action: ActionIntent, *, require_target: bool) -> None:
        params = action.parameters
        target = action.target
        token = params.get("element_token") or (target.element_token if target else None)
        index = params.get("element_index")
        x, y = params.get("x"), params.get("y")
        semantic_selector = bool(target and (target.element_name or target.element_role))
        modes = int(token is not None or semantic_selector) + int(index is not None) + int(x is not None or y is not None)
        if modes > 1:
            raise ValueError("choose exactly one UI addressing mode: semantic element, element_index, or x/y")
        if token or semantic_selector:
            await self._add_semantic_element(args, action)
            return
        if index is not None:
            snapshot_id = params.get("snapshot_id") or (target.generation if target else None)
            if not snapshot_id:
                raise ValueError("element_index requires snapshot_id/generation to prevent stale targeting")
            args["element_index"] = int(index)
            args["snapshot_id"] = snapshot_id
            return
        if x is not None or y is not None:
            if x is None or y is None:
                raise ValueError("coordinate mode requires both x and y")
            args["x"], args["y"] = x, y
            return
        if require_target:
            raise ValueError("ui.click requires a semantic element selector/token, element_index+snapshot_id, or x/y")

    async def _add_semantic_element(self, args: dict[str, Any], action: ActionIntent) -> None:
        target = action.target
        params = action.parameters
        token = params.get("element_token") or (target.element_token if target else None)
        if token:
            args["element_token"] = token
            return
        index = params.get("element_index")
        if index is not None:
            snapshot_id = params.get("snapshot_id") or (target.generation if target else None)
            if not snapshot_id:
                raise ValueError("element_index requires snapshot_id/generation to prevent stale targeting")
            args["element_index"] = int(index)
            args["snapshot_id"] = snapshot_id
            return
        if target is None or (not target.element_name and not target.element_role):
            raise ValueError("semantic action requires element_token or element_name/element_role")

        resolved_target = args.get("target") if isinstance(args.get("target"), dict) else None
        if resolved_target and resolved_target.get("kind") == "window":
            pid = int(resolved_target["pid"])
            window_id = resolved_target["window_id"]
        else:
            pid, window_id = await self._resolve_window(action)
        snapshot = await self.desktop.snapshot_window(
            pid=pid,
            window_id=window_id,
            include_screenshot=False,
            max_elements=int(params.get("selector_max_elements", 2000)),
        )
        if snapshot.degraded:
            raise CuaDriverError(
                snapshot.degraded_reason or "accessibility snapshot is degraded; semantic selector is unavailable",
                code="accessibility_degraded",
                payload=snapshot.raw,
            )
        if snapshot.truncated and not bool(params.get("allow_truncated_selector", False)):
            raise CuaDriverError(
                "accessibility snapshot is truncated; refusing to assume selector uniqueness",
                code="snapshot_truncated",
                payload={"snapshot_id": snapshot.snapshot_id},
            )
        matches = []
        for element in snapshot.elements:
            if target.element_name and (element.label or "").casefold() != target.element_name.casefold():
                continue
            if target.element_role and (element.role or "").casefold() != target.element_role.casefold():
                continue
            matches.append(element)
        if len(matches) != 1:
            raise CuaDriverError(
                f"semantic selector matched {len(matches)} elements; refusing to guess",
                code="ambiguous_element_target" if matches else "element_target_not_found",
                payload={
                    "snapshot_id": snapshot.snapshot_id,
                    "match_count": len(matches),
                    "selector": {"name": target.element_name, "role": target.element_role},
                },
            )
        element = matches[0]
        if element.element_token:
            args["element_token"] = element.element_token
            return
        if element.index is not None and snapshot.snapshot_id:
            args["element_index"] = element.index
            args["snapshot_id"] = snapshot.snapshot_id
            return
        raise CuaDriverError(
            "matched element has no stable action token",
            code="element_identity_unavailable",
            payload={"snapshot_id": snapshot.snapshot_id},
        )

    async def _resolve_application(self, target: Any):
        app = await self.desktop.find_application(
            name=target.application,
            bundle_id=target.bundle_id,
            pid=target.process_id,
        )
        if app is None:
            raise CuaDriverError("application target not found", code="application_target_not_found")
        return app

    async def _resolve_window(self, action: ActionIntent) -> tuple[int, str | int]:
        target = action.target
        params = action.parameters
        pid = params.get("pid") or (target.process_id if target else None)
        window_id = params.get("window_id") or (target.window_id if target else None)
        if pid is not None and window_id is not None:
            return int(pid), _window_id(window_id)

        if target is None:
            raise CuaDriverError("window target is missing", code="window_target_not_found")
        if pid is None:
            app = await self._resolve_application(target)
            pid = app.pid
        windows = await self.desktop.list_windows(pid=int(pid), on_screen_only=True)
        if window_id is not None:
            windows = [w for w in windows if str(w.window_id) == str(window_id)]
        elif target.window_title:
            windows = [
                w for w in windows
                if w.title and target.window_title.casefold() in w.title.casefold()
            ]
        if len(windows) != 1:
            raise CuaDriverError(
                f"window selector matched {len(windows)} windows; refusing to guess",
                code="ambiguous_window_target" if windows else "window_target_not_found",
                payload={
                    "pid": int(pid),
                    "window_title": target.window_title,
                    "candidates": [w.model_dump(mode="json") for w in windows[:20]],
                },
            )
        return int(pid), _window_id(windows[0].window_id)

    @staticmethod
    def _has_window_selector(target: Any) -> bool:
        return bool(
            target.window_id
            or target.window_title
            or target.process_id is not None
            or target.bundle_id
            or target.application
        )


def _window_id(value: Any) -> str | int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _effect(output: dict[str, Any]) -> EffectStatus:
    raw = str(output.get("effect") or "").lower()
    if raw == "confirmed" or output.get("verified") is True:
        return EffectStatus.CONFIRMED
    if raw == "suspected_noop":
        return EffectStatus.SUSPECTED_NOOP
    if raw in {"failed", "refused"}:
        return EffectStatus.FAILED
    return EffectStatus.UNVERIFIABLE


def _fallback(output: dict[str, Any]) -> str | None:
    escalation = output.get("escalation")
    if isinstance(escalation, dict):
        recommended = escalation.get("recommended")
        return str(recommended) if recommended else None
    return None
