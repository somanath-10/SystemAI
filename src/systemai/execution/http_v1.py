from __future__ import annotations

from time import perf_counter

import httpx

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.diagnostics.project_inspector import local_health_url
from systemai.execution.authorized import AuthorizedExecutor

MAX_BODY_BYTES = 64_000


def _bounded_int(value: object, *, default: int, maximum: int, name: str) -> int:
    try:
        result = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= result <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return result


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
            if not 0 < timeout <= 30:
                raise ValueError("timeout must be between 0 and 30 seconds")
            max_body = _bounded_int(action.parameters.get("max_body"), default=4096, maximum=MAX_BODY_BYTES, name="max_body")
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
                async with client.stream("GET", str(url)) as response:
                    body = bytearray()
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        remaining = max_body - len(body)
                        body.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            truncated = True
                        if len(body) == max_body:
                            truncated = True
                            break
                    output = {"url": str(url), "status_code": response.status_code, "body": bytes(body).decode(errors="replace"), "truncated": truncated, "headers": {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "server", "location"}}}
            effect = "confirmed" if output["status_code"] < 500 else "suspected_noop"
            return ActionResult(action_id=action.action_id, status="completed", effect=effect, executor=self.name, output=output, duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)
