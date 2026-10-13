from __future__ import annotations

import base64
import math
from time import perf_counter
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from systemai.cost import CostController, UsageRecord


class LocalModelUnavailable(RuntimeError):
    pass


class LocalModelResponse(BaseModel):
    text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)


class LocalEmbedding(BaseModel):
    vector: list[float]
    model: str
    digest: str
    input_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)


class OllamaClient:
    """Loopback-only inference. Model output is data, never an authorized action."""

    def __init__(self, url: str, *, small: str = "", text: str = "", vision: str = "", embedding: str = "", timeout: float = 60) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or not (parsed.port is None or 0 < parsed.port < 65536):
            raise ValueError("Ollama URL must be a plain loopback HTTP origin")
        self.url = url.rstrip("/")
        self.models = {"local_small": small, "local_llm": text, "local_vlm": vision, "local_embedding": embedding}
        self.timeout = timeout

    async def status(self) -> dict:
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=min(self.timeout, 3), trust_env=False) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                installed = {item["name"]: item.get("digest") for item in response.json()["models"] if isinstance(item, dict) and isinstance(item.get("name"), str)}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {"connected": False, "models": {kind: False for kind in self.models}, "installed_models": []}
        resolved = {kind: name if name in installed else f"{name}:latest" for kind, name in self.models.items() if name}
        return {
            "connected": True,
            "models": {kind: kind in resolved and resolved[kind] in installed for kind in self.models},
            "digests": {kind: installed.get(name) for kind, name in resolved.items() if name in installed},
            "installed_models": sorted(installed),
        }

    async def embed(self, *, task_id: str, content: str, cost: CostController) -> LocalEmbedding:
        if not content.strip() or len(content) > 4_000:
            raise ValueError("embedding input must contain 1 to 4000 characters")
        model = self.models["local_embedding"]
        if not model:
            raise LocalModelUnavailable("local embedding model is not configured")
        status = await self.status()
        digest = status.get("digests", {}).get("local_embedding")
        if not status["models"]["local_embedding"] or not isinstance(digest, str) or not digest:
            raise LocalModelUnavailable("local embedding model is not installed or has no stable digest")
        started = perf_counter()
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=self.timeout, trust_env=False) as client:
                response = await client.post("/api/embed", json={"model": model, "input": content, "truncate": False})
                response.raise_for_status()
                body = response.json()
            vector = body["embeddings"][0]
            if not isinstance(vector, list) or not 1 <= len(vector) <= 16_384 or not all(isinstance(value, (int, float)) and math.isfinite(value) and abs(value) <= 1_000_000 for value in vector) or math.isclose(sum(value * value for value in vector), 0):
                raise ValueError("invalid embedding vector")
            result = LocalEmbedding(vector=vector, model=model, digest=digest,
                                    input_tokens=body.get("prompt_eval_count", 0),
                                    latency_ms=(perf_counter() - started) * 1000)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise LocalModelUnavailable(f"local embedding request failed: {type(exc).__name__}") from exc
        cost.record(UsageRecord(task_id=task_id, provider="ollama", model=model, kind="local_embedding",
                                input_tokens=result.input_tokens, latency_ms=result.latency_ms))
        return result

    async def generate(self, *, task_id: str, prompt: str, kind: str, cost: CostController,
                       image: bytes | None = None, model_override: str | None = None) -> LocalModelResponse:
        if kind not in {"local_small", "local_llm", "local_vlm"}:
            raise ValueError("unsupported local inference tier")
        if not prompt.strip() or len(prompt) > 16_000:
            raise ValueError("prompt must contain 1 to 16000 characters")
        if image is not None and (kind != "local_vlm" or not image or len(image) > 4_000_000):
            raise ValueError("image requires local_vlm and must be at most 4 MB")
        model = model_override or self.models[kind]
        if not model:
            raise LocalModelUnavailable(f"{kind} model is not configured")
        status = await self.status()
        if model_override and model_override not in status["installed_models"]:
            raise LocalModelUnavailable("selected local model is not installed")
        if not model_override and not status["models"][kind]:
            raise LocalModelUnavailable(f"{kind} model is not installed or Ollama is unavailable")
        message: dict = {"role": "user", "content": prompt}
        if image is not None:
            message["images"] = [base64.b64encode(image).decode("ascii")]
        started = perf_counter()
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=self.timeout, trust_env=False) as client:
                response = await client.post("/api/chat", json={"model": model, "messages": [message], "stream": False, "options": {"num_predict": 2048}})
                response.raise_for_status()
                body = response.json()
            result = LocalModelResponse(
                text=body["message"]["content"], model=model,
                input_tokens=body.get("prompt_eval_count", 0), output_tokens=body.get("eval_count", 0),
                latency_ms=(perf_counter() - started) * 1000,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise LocalModelUnavailable(f"local model request failed: {type(exc).__name__}") from exc
        cost.record(UsageRecord(task_id=task_id, provider="ollama", model=model, kind=kind,
                                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                                image_count=int(image is not None), latency_ms=result.latency_ms))
        return result
