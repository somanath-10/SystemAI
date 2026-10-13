from __future__ import annotations

from time import perf_counter

import httpx

from systemai.cost import CostController, UsageRecord
from systemai.intelligence.openai_responses import OpenAIResponsesClient, OpenAIUnavailable


class OpenAISpeechClient:
    def __init__(self, provider: OpenAIResponsesClient, *, enabled: bool, stt_model: str, tts_model: str,
                 voice: str, stt_cost: float, tts_cost: float, max_segment_seconds: float = 30) -> None:
        self.provider = provider
        self.enabled = enabled
        self.stt_model, self.tts_model, self.voice = stt_model, tts_model, voice
        self.stt_cost, self.tts_cost = stt_cost, tts_cost
        self.max_segment_seconds = max_segment_seconds

    def status(self) -> dict:
        ready = self.enabled and self.provider.configured
        return {"stt": bool(ready and self.stt_model and self.stt_cost > 0),
                "tts": bool(ready and self.tts_model and self.tts_cost > 0), "provider": "openai",
                "voice": self.voice, "max_segment_seconds": self.max_segment_seconds}

    async def transcribe(self, task_id: str, audio: bytes, content_type: str, cost: CostController) -> str:
        if not self.status()["stt"]:
            raise OpenAIUnavailable("OpenAI transcription is not configured")
        types = {"audio/webm": "webm", "audio/wav": "wav", "audio/mp4": "m4a",
                 "audio/mpeg": "mp3", "audio/x-wav": "wav"}
        mime = content_type.split(";", 1)[0].lower()
        if mime not in types or not 1 <= len(audio) <= 2_000_000:
            raise ValueError("audio must be a supported recording of at most 2 MB")
        record = UsageRecord(task_id=task_id, provider="openai", model=self.stt_model, kind="specialist_api",
                             audio_seconds=self.max_segment_seconds, estimated_cost_usd=self.stt_cost,
                             metadata={"feature": "stt", "charge_basis": "configured call ceiling"})
        body = await self._request(record, cost, "/audio/transcriptions", data={"model": self.stt_model},
                                   files={"file": (f"speech.{types[mime]}", audio, mime)})
        try:
            text = body.json()["text"]
            if not isinstance(text, str):
                raise ValueError("invalid transcript")
            return text
        except (ValueError, KeyError, TypeError) as exc:
            raise OpenAIUnavailable("transcription response is malformed") from exc

    async def synthesise(self, task_id: str, text: str, cost: CostController) -> bytes:
        if not self.status()["tts"]:
            raise OpenAIUnavailable("OpenAI speech output is not configured")
        if not text.strip() or len(text) > 4096:
            raise ValueError("speech text must contain 1 to 4096 characters")
        record = UsageRecord(task_id=task_id, provider="openai", model=self.tts_model, kind="specialist_api",
                             estimated_cost_usd=self.tts_cost, audio_seconds=min(600, max(1, len(text) / 10)),
                             metadata={"feature": "tts", "charge_basis": "configured call ceiling"})
        response = await self._request(record, cost, "/audio/speech", json={"model": self.tts_model, "voice": self.voice,
                                           "input": text, "response_format": "mp3"})
        if not response.content or not response.headers.get("content-type", "").startswith("audio/"):
            raise OpenAIUnavailable("speech response contained no audio")
        return response.content

    async def _request(self, record: UsageRecord, cost: CostController, path: str, **kwargs) -> httpx.Response:
        cost.reserve_external(record)
        started = perf_counter()
        try:
            async with httpx.AsyncClient(base_url="https://api.openai.com/v1", timeout=self.provider.timeout,
                                         headers={"Authorization": f"Bearer {self.provider.api_key}"}, trust_env=False,
                                         transport=self.provider.transport) as client:
                async with client.stream("POST", path, **kwargs) as response:
                    response.raise_for_status()
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 10_000_000:
                            raise OpenAIUnavailable("speech response exceeded its size limit")
                    result = httpx.Response(response.status_code, headers=response.headers, content=bytes(chunks))
            cost.settle_external(record.model_copy(update={"latency_ms": (perf_counter() - started) * 1000}))
            return result
        except httpx.HTTPError as exc:
            raise OpenAIUnavailable(f"OpenAI speech request failed: {type(exc).__name__}") from exc
        finally:
            cost.abandon_external(record.call_id)
