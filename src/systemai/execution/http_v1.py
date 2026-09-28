from __future__ import annotations

from time import perf_counter

import httpx

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.diagnostics.project_inspector import local_health_url
from systemai.execution.authorized import AuthorizedExecutor


class HttpExecutorV1(AuthorizedExecutor):
    def __init__(self, *, verifier, event_store=None) -> None:
        super().__init__(name="http", verifier=verifier, event_store=event_store)

    def supports(self, capability: str) -> bool:
        return capability == "http.health"

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        started = perf_counter()
        url = (action.target.url if action.target else None) or action.parameters.get("url")
        if not url:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error="http.health requires URL")
        if not local_health_url(str(url)):
            return ActionResult(action_id=action.action_id, status="rejected", effect="failed", executor=self.name, error="http.health only permits loopback HTTP(S) URLs in V1")
        try:
            timeout = float(action.parameters.get("timeout", 3.0))
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
                response = await client.get(str(url))
            max_body = int(action.parameters.get("max_body", 4096))
            output = {"url": str(url), "status_code": response.status_code, "body": response.text[:max_body], "headers": {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "server", "location"}}}
            effect = "confirmed" if response.status_code < 500 else "suspected_noop"
            return ActionResult(action_id=action.action_id, status="completed", effect=effect, executor=self.name, output=output, duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)
