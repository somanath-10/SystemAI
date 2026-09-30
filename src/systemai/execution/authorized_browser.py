from __future__ import annotations

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.execution.authorized import AuthorizedExecutor
from systemai.execution.browser import PlaywrightExecutor


class AuthorizedBrowserExecutor(AuthorizedExecutor):
    def __init__(self, browser: PlaywrightExecutor, *, verifier, event_store=None) -> None:
        super().__init__(name="browser", verifier=verifier, event_store=event_store)
        self.browser = browser

    def supports(self, capability: str) -> bool:
        return self.browser.supports(capability)

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        return await self.browser.execute(action)
