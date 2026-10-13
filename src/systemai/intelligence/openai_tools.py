from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import uuid4

import httpx

from systemai.cost import CostController, UsageRecord
from systemai.intelligence.openai_responses import OpenAIResponsesClient, OpenAIUnavailable


class OpenAIToolsClient:
    def __init__(self, provider: OpenAIResponsesClient, *, search_fee: float, image_model: str, image_cost: float,
                 data_dir: Path) -> None:
        self.provider = provider
        self.search_fee, self.image_model, self.image_cost = search_fee, image_model, image_cost
        self.data_dir = data_dir

    def status(self) -> dict:
        return {"web_search": bool(self.provider.configured and self.search_fee > 0),
                "image_generation": bool(self.provider.configured and self.image_model and self.image_cost > 0)}

    async def search(self, task_id: str, prompt: str, cost: CostController) -> dict:
        if not self.status()["web_search"]:
            raise OpenAIUnavailable("OpenAI web search requires a configured tool-call rate")
        final = None
        async for event in self.provider.stream_response(task_id=task_id, input_items=[{"role": "user", "content": prompt}],
                                                         instructions="Search the web for this request and provide a concise factual answer with sources.",
                                                         tools=[{"type": "web_search"}], cost=cost, hosted_fee=self.search_fee):
            if event["type"] == "error":
                raise OpenAIUnavailable(event["message"])
            if event["type"] == "response.completed":
                final = event["response"]
        if final is None:
            raise OpenAIUnavailable("web search did not complete")
        text, sources = [], []
        for item in final.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") != "output_text":
                    continue
                text.append(part["text"])
                for annotation in part.get("annotations", []):
                    if annotation.get("type") == "url_citation" and str(annotation.get("url", "")).startswith(("https://", "http://")):
                        source = {"url": annotation["url"], "title": annotation.get("title", annotation["url"])}
                        if source not in sources:
                            sources.append(source)
        return {"text": "".join(text), "sources": sources}

    async def generate_image(self, task_id: str, prompt: str, cost: CostController) -> dict:
        if not self.status()["image_generation"]:
            raise OpenAIUnavailable("OpenAI image generation needs a model and configured call-cost ceiling")
        record = UsageRecord(task_id=task_id, provider="openai", model=self.image_model, kind="specialist_api",
                             image_count=1, estimated_cost_usd=self.image_cost,
                             metadata={"feature": "image_generation", "charge_basis": "configured call ceiling"})
        cost.reserve_external(record)
        try:
            async with httpx.AsyncClient(base_url="https://api.openai.com/v1", timeout=max(120, self.provider.timeout),
                                         headers={"Authorization": f"Bearer {self.provider.api_key}"}, trust_env=False,
                                         transport=self.provider.transport) as client:
                async with client.stream("POST", "/images/generations", json={"model": self.image_model, "prompt": prompt,
                                             "n": 1, "size": "1024x1024", "quality": "low", "output_format": "png"}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 20_000_000:
                            raise OpenAIUnavailable("generated image response is too large")
                    payload = json.loads(body)
            image = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
            if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 15_000_000:
                raise OpenAIUnavailable("image provider did not return a bounded PNG")
            artifact_id = f"image_{uuid4().hex}"
            directory = self.data_dir / "artifacts"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / f"{artifact_id}.png"
            with path.open("xb") as output:
                output.write(image)
            path.chmod(0o600)
            cost.settle_external(record)
            if cost.store:
                cost.store.append("GeneratedImageCreated", {"artifact_id": artifact_id, "path": str(path)}, task_id=task_id)
            return {"artifact_id": artifact_id, "path": str(path), "mime_type": "image/png"}
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise OpenAIUnavailable(f"OpenAI image request failed: {type(exc).__name__}") from exc
        finally:
            cost.abandon_external(record.call_id)
