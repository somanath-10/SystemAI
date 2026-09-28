from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.execution.base import Executor


class PlaywrightExecutor(Executor):
    """Optional semantic browser executor.

    Browser control is intentionally separate from desktop control: DOM/CDP-level
    actions are preferred before vision/coordinate interaction.
    """

    name = "playwright"
    CAPABILITIES = {"browser.navigate", "browser.click", "browser.fill", "browser.download"}

    def __init__(self, *, headless: bool = False) -> None:
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def _ensure(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright extra not installed: pip install 'systemai-core[browser]' && playwright install chromium") from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        context = await self._browser.new_context(accept_downloads=True)
        self._page = await context.new_page()

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        started = datetime.now(timezone.utc)
        try:
            await self._ensure()
            assert self._page is not None
            out: dict[str, Any]
            if action.capability == "browser.navigate":
                url = action.parameters.get("url") or (action.target.url if action.target else None)
                if not url:
                    raise ValueError("url is required")
                response = await self._page.goto(str(url), wait_until="domcontentloaded")
                out = {"url": self._page.url, "status": response.status if response else None}
            elif action.capability == "browser.click":
                locator = self._locator(action)
                await locator.click(timeout=int(action.parameters.get("timeout_ms", 10000)))
                out = {"url": self._page.url, "clicked": True}
            elif action.capability == "browser.fill":
                locator = self._locator(action)
                value = str(action.parameters["value"])
                await locator.fill(value)
                out = {"url": self._page.url, "filled": True}
            elif action.capability == "browser.download":
                locator = self._locator(action)
                async with self._page.expect_download(timeout=int(action.parameters.get("timeout_ms", 30000))) as info:
                    await locator.click()
                download = await info.value
                save_as = action.parameters.get("save_as")
                if save_as:
                    await download.save_as(str(save_as))
                out = {"suggested_filename": download.suggested_filename, "path": str(save_as) if save_as else await download.path()}
            else:
                raise NotImplementedError(action.capability)
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.COMPLETED,
                effect=EffectStatus.CONFIRMED,
                executor=self.name,
                output=out,
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

    def _locator(self, action: ActionIntent):
        assert self._page is not None
        role = action.parameters.get("role")
        name = action.parameters.get("name") or (action.target.element_name if action.target else None)
        selector = action.parameters.get("selector")
        if role:
            return self._page.get_by_role(role, name=name)
        if selector:
            return self._page.locator(selector)
        if name:
            return self._page.get_by_text(name, exact=bool(action.parameters.get("exact", True)))
        raise ValueError("semantic role/name or selector required")

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = self._page = self._playwright = None
