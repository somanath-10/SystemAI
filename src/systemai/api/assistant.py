from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from systemai.cost import BudgetExceeded, UsageRecord
from systemai.intelligence.openai_responses import OpenAIUnavailable

router = APIRouter()


class FunctionTool(BaseModel):
    type: Literal["function"] = "function"
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str = Field(default="", max_length=24_000)
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    strict: bool = False


class AssistantResponseRequest(BaseModel):
    input: list[dict] = Field(min_length=1, max_length=400)
    instructions: str = Field(default="", max_length=32_000)
    tools: list[FunctionTool] = Field(default_factory=list, max_length=128)
    confirm_external: Literal[True]

    @model_validator(mode="after")
    def bounded_context(self):
        if len(self.model_dump_json()) > 8_000_000:
            raise ValueError("assistant context exceeds 8 MB")
        allowed = {"message", "function_call", "function_call_output", "reasoning"}
        for item in self.input:
            if item.get("type", "message") not in allowed:
                raise ValueError("unsupported assistant input item")
        return self


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    confirm_external: Literal[True]


class AssistantToolRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    confirm_external: Literal[True]


class AssistantAuditRequest(BaseModel):
    event: Literal["AssistantTurnStarted", "AssistantTurnInterrupted", "AssistantTurnCompleted", "AssistantToolStarted", "AssistantToolCompleted", "AssistantToolFailed"]
    turn_id: str = Field(min_length=1, max_length=128)
    tool: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,128}$")


class ExternalUsageRequest(BaseModel):
    phase: Literal["reserve", "renew", "abandon", "settle"]
    worker_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    provider: str = Field(pattern=r"^(?:mcp-[a-zA-Z0-9_-]{1,32}|elevenlabs|deepgram|cartesia|sarvam)$")
    feature: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    estimated_cost_usd: float = Field(gt=0, le=10)
    audio_seconds: float = Field(default=0, ge=0, le=600)
    call_id: str | None = Field(default=None, pattern=r"^model_[0-9a-f]{16}$")


@router.post("/tasks/{task_id}/assistant/external-usage")
async def external_usage(task_id: str, body: ExternalUsageRequest, request: Request):
    runtime = _runtime(request, task_id)
    cost_id = runtime.cost_task_id(task_id)
    try:
        if body.phase == "reserve":
            record = UsageRecord(task_id=cost_id, provider=body.provider, model=body.feature, kind="specialist_api",
                                 audio_seconds=body.audio_seconds, estimated_cost_usd=body.estimated_cost_usd,
                                 metadata={"feature": body.feature, "worker_id": body.worker_id, "charge_basis": "configured connector ceiling"})
            runtime.cost.reserve_external(record)
            runtime.cost.lease_external(record.call_id, body.worker_id)
            return {"call_id": record.call_id}
        record = next((item for item in runtime.cost.records_for(cost_id) if item.call_id == body.call_id), None)
        if not record or record.provider != body.provider or record.model != body.feature or record.metadata.get("worker_id") != body.worker_id:
            raise HTTPException(404, "connector reservation not found")
        if record.metadata.get("billing_state") != "reserved" or record.estimated_cost_usd != body.estimated_cost_usd:
            raise HTTPException(409, "connector reservation is already settled or mismatched")
        if body.phase == "renew":
            runtime.cost.renew_external(record.call_id, body.worker_id)
        elif body.phase == "abandon":
            runtime.cost.abandon_external(record.call_id)
        else:
            runtime.cost.settle_external(record)
        return {"call_id": record.call_id}
    except (BudgetExceeded, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/tasks/{task_id}/assistant/events")
async def record_assistant_event(task_id: str, body: AssistantAuditRequest, request: Request):
    runtime = _runtime(request, task_id)
    event = runtime.store.append(body.event, {"turn_id": body.turn_id, "tool": body.tool}, task_id=runtime.cost_task_id(task_id))
    return {"event_id": event["event_id"]}


@router.post("/tasks/{task_id}/assistant/tools/{feature}")
async def hosted_tool(task_id: str, feature: Literal["search", "image"], body: AssistantToolRequest, request: Request):
    runtime = _runtime(request, task_id)
    if runtime.openai_tools is None:
        raise HTTPException(503, "OpenAI tools are not configured")
    try:
        method = runtime.openai_tools.search if feature == "search" else runtime.openai_tools.generate_image
        return await method(runtime.cost_task_id(task_id), body.prompt, runtime.cost)
    except BudgetExceeded as exc:
        raise HTTPException(409, str(exc)) from exc
    except OpenAIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def _runtime(request: Request, task_id: str):
    runtime = request.app.state.runtime
    if task_id not in runtime.sessions:
        raise HTTPException(404, "task not found")
    return runtime


@router.post("/assistant/sessions")
async def create_session(request: Request) -> dict:
    return request.app.state.runtime.create_assistant_session().snapshot()


@router.post("/tasks/{task_id}/assistant/response")
async def respond(task_id: str, body: AssistantResponseRequest, request: Request):
    runtime = _runtime(request, task_id)
    if runtime.openai is None:
        raise HTTPException(503, "OpenAI is not configured")

    async def events():
        async for event in runtime.openai.stream_response(task_id=runtime.cost_task_id(task_id), input_items=body.input,
                                                        instructions=body.instructions,
                                                        tools=[tool.model_dump() for tool in body.tools], cost=runtime.cost):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.post("/tasks/{task_id}/assistant/stt")
async def transcribe(task_id: str, request: Request) -> dict:
    runtime = _runtime(request, task_id)
    if runtime.speech is None:
        raise HTTPException(503, "speech is not configured")
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > 2_000_000:
            raise HTTPException(413, "audio exceeds 2 MB")
    try:
        text = await runtime.speech.transcribe(runtime.cost_task_id(task_id), bytes(audio), request.headers.get("content-type", ""), runtime.cost)
        return {"text": text}
    except BudgetExceeded as exc:
        raise HTTPException(409, str(exc)) from exc
    except OpenAIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/tasks/{task_id}/assistant/tts")
async def synthesise(task_id: str, body: SpeechRequest, request: Request):
    runtime = _runtime(request, task_id)
    if runtime.speech is None:
        raise HTTPException(503, "speech is not configured")
    try:
        audio = await runtime.speech.synthesise(runtime.cost_task_id(task_id), body.text, runtime.cost)
        return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    except BudgetExceeded as exc:
        raise HTTPException(409, str(exc)) from exc
    except OpenAIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
