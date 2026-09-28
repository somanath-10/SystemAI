from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYSTEMAI_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".systemai"
    allowed_roots: str = f"{Path.home() / 'Documents'}:{Path.home() / 'Downloads'}:/tmp"
    enable_browser: bool = False
    browser_headless: bool = False
    enable_process_monitor: bool = False
    enable_desktop: bool = False
    desktop_backend: str = "cua-cli"
    cua_driver_binary: str = "cua-driver"
    cua_driver_socket: str | None = None
    cua_timeout_seconds: float = 20.0
    desktop_session: str = "systemai"
    allow_elevation: bool = False

    @property
    def allowed_root_paths(self) -> list[Path]:
        return [Path(p).expanduser() for p in self.allowed_roots.split(":") if p]
