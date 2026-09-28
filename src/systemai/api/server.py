from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from systemai.app import AppContainer, build_container
from systemai.contracts.models import ApprovalRequest, TaskRequest


def create_api(container: AppContainer | None = None) -> FastAPI:
    container = container or build_container(planner_mode=os.getenv("SYSTEMAI_PLANNER", "rule"))
    app = FastAPI(title="SystemAI Core", version="0.2.0")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5180", "http://127.0.0.1:5180", "tauri://localhost"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/health")
    async def health():
        ok, count = container.audit.verify_chain()
        return {"status": "ok", "audit_chain_valid": ok, "audit_events": count}

    @app.get("/capabilities")
    async def capabilities():
        return [c.model_dump(mode="json") for c in container.registry.list()]

    @app.get("/desktop/status")
    async def desktop_status():
        if container.desktop is None:
            return {"configured": False, "available": False, "backend": None}
        return (await container.desktop.status()).model_dump(mode="json")

    @app.get("/desktop/apps")
    async def desktop_apps():
        if container.desktop is None:
            raise HTTPException(status_code=503, detail="desktop control is not enabled")
        return [app.model_dump(mode="json") for app in await container.desktop.list_apps()]

    @app.get("/desktop/windows")
    async def desktop_windows(pid: int | None = None):
        if container.desktop is None:
            raise HTTPException(status_code=503, detail="desktop control is not enabled")
        return [w.model_dump(mode="json") for w in await container.desktop.list_windows(pid=pid)]

    @app.get("/desktop/windows/{pid}/{window_id}/state")
    async def desktop_window_state(pid: int, window_id: str, include_screenshot: bool = False):
        if container.desktop is None:
            raise HTTPException(status_code=503, detail="desktop control is not enabled")
        snap = await container.desktop.snapshot_window(
            pid=pid, window_id=window_id, include_screenshot=include_screenshot
        )
        # Avoid sending multi-megabyte base64 screenshots by default.
        return snap.model_dump(mode="json", exclude={"screenshot_png_b64"} if not include_screenshot else set())

    @app.post("/tasks")
    async def create_task(request: TaskRequest):
        session = await container.runtime.create_task(request)
        return session.snapshot()

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        try:
            return container.runtime.get_snapshot(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc

    @app.post("/tasks/{task_id}/approvals")
    async def approve(task_id: str, request: ApprovalRequest):
        try:
            session = await container.runtime.approve(task_id, request.action_id, request.approved, request.reason)
            return session.snapshot()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task or action not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/audit")
    async def audit(limit: int = 100):
        return container.audit.list_events(min(max(limit, 1), 1000))

    @app.get("/memory/trajectories")
    async def trajectories(limit: int = 20):
        return container.memory.recent_successes(min(max(limit, 1), 200))

    return app
