from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.execution.base import Executor
from systemai.security.ephemeral import EphemeralValues
from systemai.security.origin import browser_origin


class PlaywrightExecutor(Executor):
    """Dedicated browser profile with an exact origin allowlist and semantic actions."""

    name = "browser"
    CAPABILITIES = {"browser.navigate", "browser.observe", "browser.click", "browser.fill", "browser.download", "browser.upload"}

    def __init__(
        self,
        *,
        headless: bool = False,
        channel: str = "chromium",
        profile_dir: Path | None = None,
        download_dir: Path | None = None,
        allowed_origins: set[str] | None = None,
    ) -> None:
        self.headless = headless
        self.channel = channel
        self.profile_dir = profile_dir
        self.download_dir = download_dir
        self.allowed_origins = {browser_origin(origin) for origin in (allowed_origins or set())}
        self._playwright = None
        self._context = None
        self._page = None
        self._values = EphemeralValues()

    def stash_value(self, value: str) -> str:
        return self._values.stash(value)

    def forget_value(self, reference: str) -> None:
        self._values.forget(reference)

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.allowed_origins),
            "available": importlib.util.find_spec("playwright") is not None,
            "backend": "playwright",
            "channel": self.channel,
            "allowed_origins": sorted(self.allowed_origins),
        }

    def require_origin(self, url: str) -> None:
        if browser_origin(url) not in self.allowed_origins:
            raise ValueError("browser origin is outside the configured allowlist")

    async def _route(self, route) -> None:
        url = route.request.url
        if url.startswith(("about:", "data:", "blob:")):
            await route.continue_()
            return
        try:
            self.require_origin(url)
        except ValueError:
            await route.abort("blockedbyclient")
        else:
            await route.continue_()

    async def _ensure(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed; install systemai-core[browser]") from exc
        self._playwright = await async_playwright().start()
        try:
            if self.profile_dir is not None:
                self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir) if self.profile_dir else "",
                channel=None if self.channel == "chromium" else self.channel,
                headless=self.headless,
                accept_downloads=True,
            )
            await self._context.route("**/*", self._route)
            for page in self._context.pages:
                await page.close()
            self._page = await self._context.new_page()
        except Exception:
            if self._context is not None:
                await self._context.close()
                self._context = None
            await self._playwright.stop()
            self._playwright = None
            raise

    async def current_page(self):
        await self._ensure()
        assert self._page is not None
        self.require_origin(self._page.url)
        return self._page

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        started = datetime.now(timezone.utc)
        try:
            await self._ensure()
            assert self._page is not None
            page = self._page
            out: dict[str, Any]
            if action.capability == "browser.navigate":
                url = str(action.parameters.get("url") or (action.target.url if action.target else ""))
                self.require_origin(url)
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                self.require_origin(page.url)
                out = {"url": page.url, "title": await page.title(), "status_code": response.status if response else None}
            elif action.capability == "browser.observe":
                self.require_origin(page.url)
                out = {"url": page.url, "title": await page.title()}
            else:
                self.require_origin(page.url)
                if action.target and action.target.url and page.url != action.target.url:
                    raise ValueError("browser page changed since the action was authorized")
                locator = self._locator(action)
                if await locator.count() != 1:
                    raise ValueError("browser target must resolve to exactly one element")
                if action.capability == "browser.click":
                    await locator.click(timeout=10_000)
                    out = {"url": page.url, "clicked": True}
                elif action.capability == "browser.fill":
                    if await locator.get_attribute("type") == "password":
                        raise ValueError("password fields require a Secret Broker, which is not configured")
                    reference = action.parameters.get("value_ref")
                    value = self._values.consume(str(reference))
                    await locator.fill(value, timeout=10_000)
                    out = {"url": page.url, "filled": True}
                elif action.capability == "browser.download":
                    if self.download_dir is None:
                        raise ValueError("browser download directory is not configured")
                    self.download_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                    async with page.expect_download(timeout=30_000) as download_info:
                        await locator.click()
                    download = await download_info.value
                    source = await download.path()
                    if source is None or source.stat().st_size > 50_000_000:
                        raise ValueError("browser download is unavailable or exceeds 50 MB")
                    name = Path(download.suggested_filename).name
                    destination = self.download_dir / f"{uuid4().hex}-{name}"
                    await download.save_as(destination)
                    out = {"path": str(destination), "size": destination.stat().st_size, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
                elif action.capability == "browser.upload":
                    path = Path(str(action.parameters.get("path", ""))).expanduser().resolve(strict=True)
                    if not path.is_file() or path.stat().st_size > 50_000_000:
                        raise ValueError("browser upload must be a regular file no larger than 50 MB")
                    if await locator.get_attribute("type") != "file":
                        raise ValueError("browser.upload requires a file input")
                    await locator.set_input_files(path)
                    out = {"url": page.url, "file_name": path.name, "uploaded": True}
                else:
                    raise NotImplementedError(action.capability)
            return ActionResult(action_id=action.action_id, status=ActionStatus.COMPLETED, effect=EffectStatus.CONFIRMED,
                                executor=self.name, output=out, started_at=started, finished_at=datetime.now(timezone.utc))
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status=ActionStatus.FAILED, effect=EffectStatus.FAILED,
                                executor=self.name, error=f"{type(exc).__name__}: {exc}", started_at=started, finished_at=datetime.now(timezone.utc))

    def _locator(self, action: ActionIntent):
        assert self._page is not None
        role = action.parameters.get("role")
        name = action.parameters.get("name") or (action.target.element_name if action.target else None)
        selector = action.parameters.get("selector")
        if role and name:
            return self._page.get_by_role(str(role), name=str(name), exact=True)
        if selector and isinstance(selector, str) and len(selector) <= 500:
            return self._page.locator(selector)
        if name:
            return self._page.get_by_text(str(name), exact=True)
        raise ValueError("browser action requires a semantic role/name or bounded CSS selector")

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = self._page = self._playwright = None
        self._values.clear()
