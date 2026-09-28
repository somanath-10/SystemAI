from __future__ import annotations

from typing import Any

from systemai.desktop import DesktopControlService


class DesktopVerificationProbe:
    def __init__(self, desktop: DesktopControlService) -> None:
        self.desktop = desktop

    async def application_running(self, params: dict[str, Any]) -> tuple[bool, Any]:
        app = await self.desktop.find_application(
            name=params.get("application"),
            bundle_id=params.get("bundle_id"),
            pid=params.get("pid"),
        )
        return app is not None, app.model_dump(mode="json") if app else None

    async def window_exists(self, params: dict[str, Any]) -> tuple[bool, Any]:
        app, window = await self._resolve_window(params)
        return window is not None, {
            "application": app.model_dump(mode="json") if app else None,
            "window": window.model_dump(mode="json") if window else None,
        }

    async def element_exists(self, params: dict[str, Any]) -> tuple[bool, Any]:
        _, window = await self._resolve_window(params)
        if window is None:
            return False, {"reason": "window_not_found"}
        snapshot = await self.desktop.snapshot_window(
            pid=window.pid,
            window_id=window.window_id,
            include_screenshot=False,
        )
        matches = _matching_elements(snapshot.elements, params)
        return bool(matches), {
            "snapshot_id": snapshot.snapshot_id,
            "matches": [m.model_dump(mode="json", exclude={"raw"}) for m in matches[:10]],
            "degraded": snapshot.degraded,
            "truncated": snapshot.truncated,
        }

    async def element_value_equals(self, params: dict[str, Any]) -> tuple[bool, Any]:
        _, window = await self._resolve_window(params)
        if window is None:
            return False, {"reason": "window_not_found"}
        snapshot = await self.desktop.snapshot_window(
            pid=window.pid,
            window_id=window.window_id,
            include_screenshot=False,
        )
        matches = _matching_elements(snapshot.elements, params)
        expected = params.get("value")
        passed = any(item.value == expected for item in matches)
        return passed, {
            "snapshot_id": snapshot.snapshot_id,
            "expected": expected,
            "actual_values": [item.value for item in matches[:10]],
            "match_count": len(matches),
            "degraded": snapshot.degraded,
        }

    async def _resolve_window(self, params: dict[str, Any]):
        pid = params.get("pid")
        app = None
        if pid is None:
            app = await self.desktop.find_application(
                name=params.get("application"),
                bundle_id=params.get("bundle_id"),
            )
            if app is None:
                return None, None
            pid = app.pid
        else:
            app = await self.desktop.find_application(pid=int(pid))
        window = await self.desktop.find_window(
            pid=int(pid),
            window_id=params.get("window_id"),
            title=params.get("window_title") or params.get("title"),
        )
        if window is None and not (params.get("window_id") or params.get("window_title") or params.get("title")):
            windows = await self.desktop.list_windows(pid=int(pid))
            window = windows[0] if len(windows) == 1 else None
        return app, window


def _matching_elements(elements: list[Any], params: dict[str, Any]) -> list[Any]:
    label = params.get("label") or params.get("name") or params.get("element_name")
    role = params.get("role") or params.get("element_role")
    result = []
    for element in elements:
        if label is not None and (element.label or "").casefold() != str(label).casefold():
            continue
        if role is not None and (element.role or "").casefold() != str(role).casefold():
            continue
        result.append(element)
    return result
