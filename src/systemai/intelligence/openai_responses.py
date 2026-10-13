from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import date, timedelta
from time import perf_counter

import httpx
from pydantic import BaseModel, Field

from systemai.cost import BudgetExceeded, CostController, UsageRecord


class OpenAIUnavailable(RuntimeError):
    pass


class OpenAITextResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    latency_ms: float = Field(ge=0)


class OpenAIResponsesClient:
    """Explicit metered Responses requests; function proposals confer no host authority."""

    def __init__(self, *, api_key: str, model: str, input_usd_per_million: float,
                 output_usd_per_million: float, pricing_verified_at: date | None,
                 max_input_tokens: int, max_output_tokens: int, timeout: float = 60,
                 enabled: bool = False, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self.model = model.strip()
        self.input_rate = input_usd_per_million
        self.output_rate = output_usd_per_million
        self.pricing_verified_at = pricing_verified_at
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.enabled = enabled
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.model and self.input_rate > 0
                    and self.output_rate > 0 and self.pricing_verified_at
                    and date.today() - timedelta(days=30) <= self.pricing_verified_at <= date.today())

    def status(self) -> dict:
        return {"configured": self.configured, "model": self.model if self.configured else None,
                "pricing_verified_at": self.pricing_verified_at.isoformat() if self.configured else None}

    async def generate(self, *, task_id: str, prompt: str, cost: CostController, image: bytes | None = None) -> OpenAITextResponse:
        if not self.configured:
            raise OpenAIUnavailable("OpenAI is not enabled with a key, model, and verified price settings")
        if not prompt.strip() or len(prompt) > 16_000:
            raise ValueError("prompt must contain 1 to 16000 characters")
        if image is not None and (not image or len(image) > 4_000_000):
            raise ValueError("image must be at most 4 MB")
        mime = "image/png" if image and image.startswith(b"\x89PNG\r\n\x1a\n") else \
               "image/jpeg" if image and image.startswith(b"\xff\xd8\xff") else \
               "image/webp" if image and image.startswith(b"RIFF") and image[8:12] == b"WEBP" else None
        if image is not None and mime is None:
            raise ValueError("image must be PNG, JPEG or WebP")
        minimum = self.max_output_tokens * self.output_rate / 1_000_000
        allowed, reason = cost.can_use_external(task_id, estimated_cost_usd=minimum, vision=image is not None)
        if not allowed:
            raise BudgetExceeded(reason)
        content: str | list[dict] = prompt
        if image is not None:
            content = [{"type": "input_text", "text": prompt},
                       {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"}]
        request = {"model": self.model, "input": [{"role": "user", "content": content}]}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url="https://api.openai.com/v1", headers=headers,
                                     timeout=self.timeout, trust_env=False, transport=self.transport) as client:
            count = await self._post(client, "/responses/input_tokens", request)
            tokens = count.get("input_tokens")
            if type(tokens) is not int or tokens < 0:
                raise OpenAIUnavailable("OpenAI returned an invalid input token count")
            if tokens > self.max_input_tokens:
                raise BudgetExceeded("OpenAI input token limit exceeded")
            reservation = (tokens * self.input_rate + self.max_output_tokens * self.output_rate) / 1_000_000
            record = UsageRecord(task_id=task_id, provider="openai", model=self.model, kind="standard_api",
                                 image_count=int(image is not None), estimated_cost_usd=reservation)
            cost.reserve_external(record)
            started = perf_counter()
            try:
                body = await self._post(client, "/responses", {**request, "max_output_tokens": self.max_output_tokens,
                                                                "service_tier": "default", "store": False, "tools": []})
            finally:
                cost.abandon_external(record.call_id)
        input_tokens, output_tokens, actual, latency = self._settle_response(body, record, cost, started)
        output = body.get("output")
        if not isinstance(output, list):
            raise OpenAIUnavailable("OpenAI response output is malformed")
        pieces = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message" or not isinstance(item.get("content"), list):
                continue
            pieces.extend(part["text"] for part in item["content"] if isinstance(part, dict)
                          and part.get("type") == "output_text" and isinstance(part.get("text"), str))
        text = "".join(pieces)
        if not text:
            raise OpenAIUnavailable("OpenAI response contained no text")
        return OpenAITextResponse(text=text, model=self.model, input_tokens=input_tokens,
                                  output_tokens=output_tokens, estimated_cost_usd=actual, latency_ms=latency)

    def _settle_response(self, body: dict, record: UsageRecord, cost: CostController, started: float) -> tuple[int, int, float, float]:
        if body.get("status") != "completed" or body.get("model") != self.model or body.get("service_tier") != "default":
            raise OpenAIUnavailable("OpenAI response was incomplete or used an unexpected model or tier; reservation remains held")
        usage = body.get("usage") or {}
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
        if any(type(value) is not int or value < 0 for value in (input_tokens, output_tokens)):
            raise OpenAIUnavailable("OpenAI response usage is missing; reservation remains held")
        if usage.get("total_tokens") != input_tokens + output_tokens:
            raise OpenAIUnavailable("OpenAI response token totals are inconsistent; reservation remains held")
        if input_tokens > self.max_input_tokens or output_tokens > self.max_output_tokens:
            raise OpenAIUnavailable("OpenAI response exceeded configured token bounds; reservation remains held")
        actual = (input_tokens * self.input_rate + output_tokens * self.output_rate) / 1_000_000 + record.metadata.get("hosted_fee", 0)
        latency = (perf_counter() - started) * 1000
        cost.settle_external(record.model_copy(update={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                               "estimated_cost_usd": actual, "latency_ms": latency}))
        return input_tokens, output_tokens, actual, latency

    async def stream_response(self, *, task_id: str, input_items: list[dict], instructions: str,
                              tools: list[dict], cost: CostController, hosted_fee: float = 0) -> AsyncIterator[dict]:
        """Stream proposals and text; declared functions are executed by the bridge, never here."""
        record = None
        try:
            if not self.configured:
                raise OpenAIUnavailable("OpenAI needs a server-side key, model, verified rates, and enabled configuration")
            request = {"model": self.model, "input": input_items, "instructions": instructions, "tools": tools}
            vision = '"input_image"' in json.dumps(input_items)
            cost.require_external_budget(task_id, estimated_cost_usd=self.max_output_tokens * self.output_rate / 1_000_000,
                                         vision=vision)
            async with httpx.AsyncClient(base_url="https://api.openai.com/v1", timeout=self.timeout,
                                         headers={"Authorization": f"Bearer {self.api_key}"}, trust_env=False,
                                         transport=self.transport) as client:
                count = await self._post(client, "/responses/input_tokens", request)
                tokens = count.get("input_tokens")
                if type(tokens) is not int or not 0 <= tokens <= self.max_input_tokens:
                    raise BudgetExceeded("assistant input token limit exceeded")
                record = UsageRecord(task_id=task_id, provider="openai", model=self.model, kind="standard_api",
                                     image_count=int(vision), metadata={"feature": "web_search" if hosted_fee else "assistant", "hosted_fee": hosted_fee},
                                     estimated_cost_usd=((self.max_input_tokens if hosted_fee else tokens) * self.input_rate +
                                                         self.max_output_tokens * self.output_rate) / 1_000_000 + hosted_fee)
                cost.reserve_external(record)
                started = perf_counter()
                params = {**request, "max_output_tokens": self.max_output_tokens, "service_tier": "default",
                          "store": False, "stream": True, "include": ["reasoning.encrypted_content"]}
                if hosted_fee:
                    params["max_tool_calls"] = 1
                async with client.stream("POST", "/responses", json=params) as response:
                    response.raise_for_status()
                    total_bytes = 0
                    async for line in response.aiter_lines():
                        total_bytes += len(line)
                        if total_bytes > 16_000_000:
                            raise OpenAIUnavailable("assistant stream exceeded its size limit")
                        if not line.startswith("data: ") or line[6:] == "[DONE]":
                            continue
                        event = json.loads(line[6:])
                        if event.get("type") == "response.completed":
                            self._settle_response(event["response"], record, cost, started)
                            yield event
                            return
                        if event.get("type") in {"response.failed", "response.incomplete", "error"}:
                            raise OpenAIUnavailable("assistant response did not complete; charge reservation remains held")
                        if event.get("type") in {"response.output_text.delta", "response.output_item.added"}:
                            yield event
                raise OpenAIUnavailable("assistant stream ended without final usage")
        except (OpenAIUnavailable, BudgetExceeded, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            message = str(exc) if isinstance(exc, (OpenAIUnavailable, BudgetExceeded)) else f"assistant request failed: {type(exc).__name__}"
            yield {"type": "error", "message": message}
        finally:
            if record is not None:
                cost.abandon_external(record.call_id)

    @staticmethod
    async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
        try:
            response = await client.post(path, json=body)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("invalid response")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenAIUnavailable(f"OpenAI request failed: {type(exc).__name__}") from exc
