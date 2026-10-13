from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
from pydantic import BaseModel, Field

from systemai.config import Settings
from systemai.api.assistant import router as assistant_router
from systemai.cost import BudgetExceeded
from systemai.desktop import DesktopToolClient
from systemai.intelligence import RoutingRequest
from systemai.intelligence.ollama import LocalModelUnavailable
from systemai.intelligence.openai_responses import OpenAIUnavailable
from systemai.runtime import VERSION, build_runtime


class DiagnoseRequest(BaseModel):
    project_root: str
    goal: str = "Find why this project is not running and fix it."
    autonomy_mode: Literal["observe", "assist", "standard_auto"] = "standard_auto"


class ApprovalBody(BaseModel):
    action_id: str
    approved: bool
    reason: str | None = None


class BrowserTaskRequest(BaseModel):
    capability: Literal["browser.navigate", "browser.observe", "browser.click", "browser.fill", "browser.download", "browser.upload"]
    url: str
    selector: str | None = None
    role: str | None = None
    name: str | None = None
    value: str | None = None
    path: str | None = None
    expected_url: str | None = None
    expected_title: str | None = None
    expected_text: str | None = None


class DesktopTaskRequest(BaseModel):
    capability: Literal["application.launch", "window.observe", "ui.click", "ui.set_value"]
    bundle_id: str
    window_title: str | None = None
    element_name: str | None = None
    element_role: str | None = None
    value: str | None = None
    verify_element_name: str | None = None
    verify_window_title: str | None = None


class LocalInferenceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    small: bool = False
    model: str | None = Field(default=None, min_length=1, max_length=200)
    image_base64: str | None = Field(default=None, max_length=5_400_000)


class OpenAIInferenceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    image_base64: str | None = Field(default=None, max_length=5_400_000)
    confirm_external: Literal[True]


def _decode_image(value: str | None) -> bytes | None:
    if value is None:
        return None
    try:
        image = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail="invalid base64 image") from exc
    if not (image.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (image.startswith(b"RIFF") and image[8:12] == b"WEBP")):
        raise HTTPException(status_code=400, detail="image must be PNG, JPEG or WebP")
    return image


class MemoryNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=10)


class MonitorRuleRequest(BaseModel):
    event_type: Literal["PROCESS_STARTED", "PROCESS_EXITED"]
    process_name: str = Field(min_length=1, max_length=200)
    cooldown_seconds: int = Field(default=60, ge=0, le=86400)


class MonitorRuleState(BaseModel):
    enabled: bool


class SkillCandidateReviewRequest(BaseModel):
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["retain", "reject"]


def create_app(data_dir: Path | None = None, *, desktop_client: DesktopToolClient | None = None, settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            await runtime.start_monitoring()
            yield
        finally:
            await runtime.stop_monitoring()
            if runtime.browser:
                await runtime.browser.close()

    app = FastAPI(title="SystemAI Local Control API", version=VERSION, lifespan=lifespan)
    local_ui_origins = {"http://localhost:5802", "http://127.0.0.1:5802", "tauri://localhost"}
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(local_ui_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def reject_untrusted_browser_writes(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in local_ui_origins:
                return JSONResponse({"detail": "untrusted browser origin"}, status_code=403)
        return await call_next(request)
    settings = settings or Settings(_env_file=None if data_dir is not None else ".env")
    data_dir = data_dir or settings.data_dir
    runtime = build_runtime(data_dir=data_dir, desktop_client=desktop_client, settings=settings)
    app.state.runtime = runtime
    app.include_router(assistant_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": VERSION, "event_chain_valid": runtime.store.verify_chain()}

    @app.get("/capabilities")
    async def capabilities() -> dict:
        return {"items": [x.model_dump(mode="json") for x in runtime.security_kernel.registry.list()]}

    @app.get("/desktop/status")
    async def desktop_status() -> dict:
        if runtime.desktop is None:
            return {"configured": False, "available": False, "backend": "none", "allowed_applications": []}
        status = await runtime.desktop.status()
        return {**status.model_dump(mode="json"), "allowed_applications": sorted(runtime.allowed_applications)}

    @app.get("/browser/status")
    async def browser_status() -> dict:
        return runtime.browser.status() if runtime.browser else {"configured": False, "available": False, "backend": "none"}

    @app.get("/monitor/status")
    async def monitor_status() -> dict:
        return runtime.monitoring_status() | {"rules": len(runtime.store.monitor_rules())}

    @app.get("/monitor/rules")
    async def monitor_rules() -> dict:
        return {"items": runtime.store.monitor_rules()}

    @app.post("/monitor/rules")
    async def create_monitor_rule(request: MonitorRuleRequest) -> dict:
        if runtime.process_monitor is None:
            raise HTTPException(status_code=409, detail="process monitor is disabled")
        rule = runtime.store.add_monitor_rule(request.event_type, request.process_name, request.cooldown_seconds)
        runtime.store.append("MonitorRuleCreated", rule)
        return rule

    @app.post("/monitor/rules/{rule_id}/state")
    async def set_monitor_rule_state(rule_id: str, request: MonitorRuleState) -> dict:
        if not runtime.store.set_monitor_rule_enabled(rule_id, request.enabled):
            raise HTTPException(status_code=404, detail="monitor rule not found")
        runtime.store.append("MonitorRuleStateChanged", {"rule_id": rule_id, "enabled": request.enabled})
        return {"rule_id": rule_id, "enabled": request.enabled}

    @app.get("/inference/status")
    async def inference_status() -> dict:
        return await runtime.local_model_status()

    @app.post("/tasks/browser")
    async def browser_task(req: BrowserTaskRequest, parent_task_id: str | None = None) -> dict:
        try:
            session = await runtime.create_browser_task(**req.model_dump(), parent_task_id=parent_task_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/desktop-observation")
    async def desktop_observation(parent_task_id: str | None = None) -> dict:
        try:
            session = await runtime.create_desktop_observation(parent_task_id=parent_task_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/desktop")
    async def desktop_task(req: DesktopTaskRequest, parent_task_id: str | None = None) -> dict:
        try:
            session = await runtime.create_desktop_task(**req.model_dump(), parent_task_id=parent_task_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/developer-diagnosis")
    async def create_diagnosis(req: DiagnoseRequest, parent_task_id: str | None = None) -> dict:
        root = Path(req.project_root).expanduser()
        if not root.exists() or not root.is_dir():
            raise HTTPException(status_code=400, detail="project_root must be an existing directory")
        try:
            session = await runtime.create_developer_task(req.goal, root, autonomy_mode=req.autonomy_mode, parent_task_id=parent_task_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.snapshot()

    @app.get("/tasks")
    async def task_history(limit: int = Query(default=100, ge=1, le=200)) -> dict:
        return {"items": [{"task_id": task.task_id, "objective": task.contract.objective,
                           "state": task.state.value, "parent_task_id": task.parent_task_id}
                          for task in list(runtime.sessions.values())[-limit:][::-1]]}

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found in this process")
        return runtime.sessions[task_id].snapshot()

    @app.get("/tasks/{task_id}/cost")
    async def task_cost(task_id: str) -> dict:
        try:
            return runtime.cost_summary(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc

    @app.get("/tasks/{task_id}/skill-candidate")
    async def skill_candidate(task_id: str) -> dict:
        try:
            return runtime.skill_candidate(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc

    @app.post("/tasks/{task_id}/skill-candidate/review")
    async def review_skill_candidate(task_id: str, request: SkillCandidateReviewRequest) -> dict:
        try:
            return runtime.review_skill_candidate(task_id, request.candidate_hash, request.decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/inference/route")
    async def route_inference(task_id: str, request: RoutingRequest) -> dict:
        if request.task_id != task_id:
            raise HTTPException(status_code=400, detail="routing task_id does not match path")
        try:
            return (await runtime.route_inference(request)).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/inference/generate")
    async def generate_local(task_id: str, request: LocalInferenceRequest) -> dict:
        image = _decode_image(request.image_base64)
        try:
            return await runtime.generate_local(task_id, request.prompt, small=request.small,
                                                vision_image=image, model_override=request.model)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except LocalModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/inference/openai")
    async def generate_openai(task_id: str, request: OpenAIInferenceRequest) -> dict:
        image = _decode_image(request.image_base64)
        try:
            return await runtime.generate_openai(task_id, request.prompt, vision_image=image)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except BudgetExceeded as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OpenAIUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/memory")
    async def add_memory(task_id: str, request: MemoryNoteRequest) -> dict:
        try:
            return await runtime.add_memory(task_id, request.content)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except LocalModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/memory/search")
    async def search_memory(task_id: str, request: MemorySearchRequest) -> dict:
        try:
            return await runtime.search_memory(task_id, request.query, request.limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except LocalModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/tasks/{task_id}/memory/{note_id}")
    async def delete_memory(task_id: str, note_id: str) -> dict:
        try:
            runtime.delete_memory(task_id, note_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory note not found") from exc
        return {"deleted": True}

    @app.post("/tasks/{task_id}/approval")
    async def approve(task_id: str, body: ApprovalBody) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            runtime.approve(task_id, body.action_id, approved=body.approved, reason=body.reason)
            if body.approved:
                await runtime.run(task_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return runtime.sessions[task_id].snapshot()

    @app.post("/tasks/{task_id}/pause")
    async def pause(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            runtime.pause(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return runtime.sessions[task_id].snapshot()

    @app.post("/tasks/{task_id}/resume")
    async def resume(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            session = await runtime.resume(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/{task_id}/take-control")
    async def takeover(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            runtime.take_control(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return runtime.sessions[task_id].snapshot()

    @app.post("/tasks/{task_id}/cancel")
    async def cancel(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            runtime.cancel(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return runtime.sessions[task_id].snapshot()

    @app.get("/approvals/{approval_id}")
    async def approval(approval_id: str) -> dict:
        record = runtime.security_kernel.approvals.get(approval_id)
        if not record:
            raise HTTPException(status_code=404, detail="approval not found")
        return record

    @app.get("/events")
    async def events(task_id: str | None = None, limit: int = 200, latest: bool = False) -> dict:
        return {"items": runtime.store.list_events(task_id=task_id, limit=limit, latest=latest)}

    return app


app = create_app()
