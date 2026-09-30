from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
from pydantic import BaseModel

from systemai.config import Settings
from systemai.desktop import DesktopToolClient
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


def create_app(data_dir: Path | None = None, *, desktop_client: DesktopToolClient | None = None, settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if runtime.browser:
                await runtime.browser.close()

    app = FastAPI(title="SystemAI Local Control API", version=VERSION, lifespan=lifespan)
    local_ui_origins = {"http://localhost:5802", "http://127.0.0.1:5802", "tauri://localhost"}
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(local_ui_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
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

    @app.post("/tasks/browser")
    async def browser_task(req: BrowserTaskRequest) -> dict:
        try:
            session = await runtime.create_browser_task(**req.model_dump())
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/desktop-observation")
    async def desktop_observation() -> dict:
        try:
            session = await runtime.create_desktop_observation()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/desktop")
    async def desktop_task(req: DesktopTaskRequest) -> dict:
        try:
            session = await runtime.create_desktop_task(**req.model_dump())
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return session.snapshot()

    @app.post("/tasks/developer-diagnosis")
    async def create_diagnosis(req: DiagnoseRequest) -> dict:
        root = Path(req.project_root).expanduser()
        if not root.exists() or not root.is_dir():
            raise HTTPException(status_code=400, detail="project_root must be an existing directory")
        session = await runtime.create_developer_task(req.goal, root, autonomy_mode=req.autonomy_mode)
        return session.snapshot()

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found in this process")
        return runtime.sessions[task_id].snapshot()

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
        runtime.pause(task_id)
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
        runtime.take_control(task_id)
        return runtime.sessions[task_id].snapshot()

    @app.post("/tasks/{task_id}/cancel")
    async def cancel(task_id: str) -> dict:
        if task_id not in runtime.sessions:
            raise HTTPException(status_code=404, detail="task not found")
        runtime.cancel(task_id)
        return runtime.sessions[task_id].snapshot()

    @app.get("/approvals/{approval_id}")
    async def approval(approval_id: str) -> dict:
        record = runtime.security_kernel.approvals.get(approval_id)
        if not record:
            raise HTTPException(status_code=404, detail="approval not found")
        return record

    @app.get("/events")
    async def events(task_id: str | None = None, limit: int = 200) -> dict:
        return {"items": runtime.store.list_events(task_id=task_id, limit=limit)}

    return app


app = create_app()
