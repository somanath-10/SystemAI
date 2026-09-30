from __future__ import annotations

from typing import Any, Protocol

from systemai.contracts.desktop import (
    DesktopApplication,
    DesktopDriverStatus,
    DesktopElement,
    DesktopSnapshot,
    DesktopWindow,
)


class DesktopToolClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...

    async def status(self) -> DesktopDriverStatus: ...


class DesktopControlService:
    """Read-oriented facade around the desktop driver.

    The agent execution path still goes through PolicyKernel + ExecutionGateway.
    This service is for readiness checks, observation, verification, and operator UI.
    """

    def __init__(self, client: DesktopToolClient, *, session: str = "systemai") -> None:
        self.client = client
        self.session = session

    async def status(self) -> DesktopDriverStatus:
        return await self.client.status()

    async def list_apps(self) -> list[DesktopApplication]:
        raw = await self.client.call_tool("list_apps", {})
        payload = _unwrap(raw)
        if not any(key in payload for key in ("apps", "applications", "items")):
            raise ValueError("desktop driver did not return an application list")
        rows = payload.get("apps") or payload.get("applications") or payload.get("items") or []
        result: list[DesktopApplication] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            pid = item.get("pid") or item.get("process_id")
            name = item.get("name") or item.get("application") or item.get("localized_name")
            if pid is None or not name:
                continue
            result.append(
                DesktopApplication(
                    name=str(name),
                    pid=int(pid),
                    bundle_id=item.get("bundle_id") or item.get("bundleId"),
                    path=item.get("path") or item.get("bundle_path"),
                    running=bool(item.get("running", True)),
                    frontmost=item.get("frontmost"),
                    windows=item.get("windows") or [],
                )
            )
        return result

    async def list_windows(self, *, pid: int | None = None, on_screen_only: bool = True) -> list[DesktopWindow]:
        args: dict[str, Any] = {"on_screen_only": on_screen_only}
        if pid is not None:
            args["pid"] = pid
        raw = await self.client.call_tool("list_windows", args)
        payload = _unwrap(raw)
        rows = payload.get("windows") or payload.get("items") or []
        result: list[DesktopWindow] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            item_pid = item.get("pid") or pid
            window_id = item.get("window_id") or item.get("windowId") or item.get("id")
            if item_pid is None or window_id is None:
                continue
            result.append(
                DesktopWindow(
                    pid=int(item_pid),
                    window_id=str(window_id),
                    title=item.get("title"),
                    application=item.get("application") or item.get("app_name"),
                    bundle_id=item.get("bundle_id") or item.get("bundleId"),
                    on_screen=item.get("on_screen") if "on_screen" in item else item.get("onScreen"),
                    frame=item.get("frame") or {},
                )
            )
        return result

    async def snapshot_window(
        self,
        *,
        pid: int,
        window_id: str | int,
        include_screenshot: bool = True,
        max_elements: int | None = None,
    ) -> DesktopSnapshot:
        args: dict[str, Any] = {
            "pid": pid,
            "window_id": _coerce_window_id(window_id),
            "include_screenshot": include_screenshot,
            "session": self.session,
        }
        if max_elements is not None:
            args["max_elements"] = max_elements
        raw = await self.client.call_tool("get_window_state", args)
        return normalize_snapshot(raw, kind="window", pid=pid, window_id=str(window_id))

    async def snapshot_desktop(self, *, display_id: str = "primary") -> DesktopSnapshot:
        raw = await self.client.call_tool("get_desktop_state", {"session": self.session})
        return normalize_snapshot(raw, kind="desktop", display_id=display_id)

    async def find_application(
        self,
        *,
        name: str | None = None,
        bundle_id: str | None = None,
        pid: int | None = None,
    ) -> DesktopApplication | None:
        apps = await self.list_apps()
        for app in apps:
            if pid is not None and app.pid == pid:
                return app
            if bundle_id and app.bundle_id == bundle_id:
                return app
            if name and app.name.casefold() == name.casefold():
                return app
        return None

    async def find_window(
        self,
        *,
        pid: int,
        window_id: str | None = None,
        title: str | None = None,
    ) -> DesktopWindow | None:
        windows = await self.list_windows(pid=pid)
        for window in windows:
            if window_id is not None and str(window.window_id) == str(window_id):
                return window
            if title and window.title and title.casefold() in window.title.casefold():
                return window
        return None


def _unwrap(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    structured = raw.get("structured_json")
    if isinstance(structured, dict):
        return structured
    if isinstance(structured, str):
        import json

        try:
            parsed = json.loads(structured)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return raw


def normalize_snapshot(
    raw: dict[str, Any],
    *,
    kind: str,
    pid: int | None = None,
    window_id: str | None = None,
    display_id: str | None = None,
) -> DesktopSnapshot:
    payload = _unwrap(raw)
    elements: list[DesktopElement] = []
    for idx, item in enumerate(payload.get("elements") or []):
        if not isinstance(item, dict):
            continue
        elements.append(
            DesktopElement(
                index=item.get("index", idx),
                element_token=item.get("element_token") or item.get("elementToken"),
                role=item.get("role"),
                label=item.get("label") or item.get("name") or item.get("title"),
                value=item.get("value"),
                enabled=item.get("enabled"),
                focused=item.get("focused"),
                frame=item.get("frame") or item.get("bounds") or {},
                actions=item.get("actions") or [],
                raw=item,
            )
        )

    screenshot = payload.get("screenshot_png_b64") or payload.get("screenshotPngB64")
    if not screenshot:
        for image in raw.get("images") or []:
            if not isinstance(image, dict):
                continue
            mime = image.get("mime_type") or image.get("mimeType")
            data = image.get("data_base64") or image.get("dataBase64")
            if mime == "image/png" and data:
                screenshot = data
                break

    return DesktopSnapshot(
        kind=kind,  # type: ignore[arg-type]
        pid=pid or payload.get("pid"),
        window_id=window_id or _string_or_none(payload.get("window_id") or payload.get("windowId")),
        display_id=display_id,
        snapshot_id=payload.get("snapshot_id") or payload.get("snapshotId"),
        tree_markdown=payload.get("tree_markdown") or payload.get("treeMarkdown"),
        elements=elements,
        screenshot_png_b64=screenshot,
        screenshot_mime_type=payload.get("screenshot_mime_type") or payload.get("screenshotMimeType") or ("image/png" if screenshot else None),
        screenshot_width=_int_or_none(payload.get("screenshot_width") or payload.get("screenshotWidth") or payload.get("width")),
        screenshot_height=_int_or_none(payload.get("screenshot_height") or payload.get("screenshotHeight") or payload.get("height")),
        degraded=bool(payload.get("degraded", raw.get("degraded", False))),
        degraded_reason=payload.get("degraded_reason") or payload.get("degradedReason"),
        truncated=bool(payload.get("truncated", False)),
        raw=payload,
    )


def _coerce_window_id(value: str | int) -> str | int:
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None
