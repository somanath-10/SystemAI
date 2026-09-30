from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYSTEMAI_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".systemai" / "runtime"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    autonomy_mode: str = "standard_auto"
    allowed_roots: str = f"{Path.home() / 'Documents'}:{Path.home() / 'Downloads'}:/tmp"
    enable_browser: bool = False
    browser_headless: bool = False
    browser_channel: str = "chromium"
    browser_allowed_origins: str = "http://127.0.0.1:5802,http://localhost:5802"
    browser_profile_dir: Path | None = None
    browser_download_dir: Path | None = None
    enable_process_monitor: bool = False
    enable_desktop: bool = False
    desktop_backend: str = "cua-cli"
    desktop_allowed_apps: str = "com.apple.finder,com.apple.TextEdit,com.apple.calculator,com.google.Chrome,com.microsoft.VSCode"
    cua_driver_binary: str = "cua-driver"
    cua_driver_socket: str | None = None
    cua_timeout_seconds: float = 20.0
    desktop_session: str = "systemai"
    allow_elevation: bool = False

    @property
    def allowed_root_paths(self) -> list[Path]:
        return [Path(p).expanduser() for p in self.allowed_roots.split(":") if p]

    @property
    def browser_origins(self) -> set[str]:
        return {origin.strip().rstrip("/") for origin in self.browser_allowed_origins.split(",") if origin.strip()}

    @property
    def desktop_app_ids(self) -> set[str]:
        return {item.strip() for item in self.desktop_allowed_apps.split(",") if item.strip()}
