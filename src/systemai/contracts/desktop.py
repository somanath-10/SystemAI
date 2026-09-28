from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DesktopPermissionStatus(BaseModel):
    accessibility: bool | None = None
    screen_recording: bool | None = None
    direct_capture_status: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.accessibility is True and self.screen_recording is True


class DesktopApplication(BaseModel):
    name: str
    pid: int
    bundle_id: str | None = None
    path: str | None = None
    running: bool = True
    frontmost: bool | None = None
    windows: list[dict[str, Any]] = Field(default_factory=list)


class DesktopWindow(BaseModel):
    pid: int
    window_id: str
    title: str | None = None
    application: str | None = None
    bundle_id: str | None = None
    on_screen: bool | None = None
    frame: dict[str, Any] = Field(default_factory=dict)


class DesktopElement(BaseModel):
    index: int | None = None
    element_token: str | None = None
    role: str | None = None
    label: str | None = None
    value: Any = None
    enabled: bool | None = None
    focused: bool | None = None
    frame: dict[str, Any] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class DesktopSnapshot(BaseModel):
    kind: Literal["window", "desktop"]
    pid: int | None = None
    window_id: str | None = None
    display_id: str | None = None
    snapshot_id: str | None = None
    tree_markdown: str | None = None
    elements: list[DesktopElement] = Field(default_factory=list)
    screenshot_png_b64: str | None = None
    screenshot_mime_type: str | None = None
    screenshot_width: int | None = None
    screenshot_height: int | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    truncated: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class DesktopDriverStatus(BaseModel):
    configured: bool
    available: bool
    backend: str
    version: str | None = None
    daemon_status: str | None = None
    permissions: DesktopPermissionStatus | None = None
    details: dict[str, Any] = Field(default_factory=dict)
