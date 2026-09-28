from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from systemai.v1 import VERSION, build_v1_runtime


class DiagnoseRequest(BaseModel):
    project_root: str
    goal: str = "Find why this project is not running and fix it."
    autonomy_mode: Literal["observe", "assist", "standard_auto"] = "standard_auto"


class ApprovalBody(BaseModel):
    action_id: str
    approved: bool
    reason: str | None = None


def create_app(data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="SystemAI V1 Local Control API", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5180",
            "http://127.0.0.1:5180",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    data_dir = data_dir or Path(os.environ.get("SYSTEMAI_DATA_DIR", str(Path.home() / ".systemai" / "v1")))
    runtime = build_v1_runtime(data_dir=data_dir)
    app.state.runtime = runtime

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": VERSION, "event_chain_valid": runtime.store.verify_chain()}

    @app.get("/capabilities")
    async def capabilities() -> dict:
        return {"items": [x.model_dump(mode="json") for x in runtime.security_kernel.registry.list()]}

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
        return {"items": runtime.store.list_events(task_id=task_id, limit=min(limit, 1000))}

    return app


app = create_app()
