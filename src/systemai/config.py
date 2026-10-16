from __future__ import annotations

from pathlib import Path
from datetime import date

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYSTEMAI_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".systemai" / "runtime"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    api_token: SecretStr = SecretStr("")
    autonomy_mode: str = "standard_auto"
    allowed_roots: str = f"{Path.home() / 'Documents'}:{Path.home() / 'Downloads'}:/tmp"
    enable_browser: bool = False
    browser_headless: bool = False
    browser_channel: str = "chromium"
    browser_allowed_origins: str = "http://127.0.0.1:5802,http://localhost:5802"
    browser_profile_dir: Path | None = None
    browser_download_dir: Path | None = None
    enable_process_monitor: bool = False
    process_monitor_interval_seconds: float = Field(default=2.0, gt=0)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_small_model: str = ""
    ollama_text_model: str = ""
    ollama_vision_model: str = ""
    ollama_embedding_model: str = ""
    ollama_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    enable_openai: bool = False
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias=AliasChoices("OPENAI_API_KEY", "SYSTEMAI_OPENAI_API_KEY"))
    openai_model: str = ""
    openai_input_usd_per_million: float = Field(default=0.0, ge=0)
    openai_output_usd_per_million: float = Field(default=0.0, ge=0)
    openai_pricing_verified_at: date | None = None
    openai_max_input_tokens: int = Field(default=8192, ge=1, le=1_000_000)
    openai_max_output_tokens: int = Field(default=512, ge=16, le=100_000)
    openai_max_task_spend_usd: float = Field(default=0.0, ge=0, le=100)
    openai_max_task_calls: int = Field(default=0, ge=0, le=100)
    openai_max_task_vision_calls: int = Field(default=0, ge=0, le=100)
    openai_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    enable_openai_speech: bool = False
    openai_stt_model: str = "gpt-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "cedar"
    openai_stt_max_call_cost_usd: float = Field(default=0, ge=0, le=10)
    openai_tts_max_call_cost_usd: float = Field(default=0, ge=0, le=10)
    openai_max_task_audio_seconds: float = Field(default=120, ge=0, le=86_400)
    openai_web_search_usd_per_call: float = Field(default=0, ge=0, le=10)
    openai_image_model: str = ""
    openai_image_max_call_cost_usd: float = Field(default=0, ge=0, le=10)
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
