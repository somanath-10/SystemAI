from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from systemai.contracts.models import ActionIntent, ActionResult, ActionStatus, EffectStatus
from systemai.execution.base import Executor


class LocalExecutor(Executor):
    """Bounded host operations. Destructive authorization is handled by PolicyKernel."""

    name = "local"
    CAPABILITIES = {
        "file.read",
        "file.write",
        "file.move",
        "file.delete",
        "directory.list",
        "directory.create",
        "process.list",
        "application.launch",
    }

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute(self, action: ActionIntent, *, capability_token: str | None = None) -> ActionResult:
        started = datetime.now(timezone.utc)
        try:
            output = await self._dispatch(action)
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.COMPLETED,
                effect=EffectStatus.CONFIRMED,
                executor=self.name,
                output=output,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # executor boundary captures, runtime decides recovery
            return ActionResult(
                action_id=action.action_id,
                status=ActionStatus.FAILED,
                effect=EffectStatus.FAILED,
                executor=self.name,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )

    async def _dispatch(self, action: ActionIntent) -> dict[str, Any]:
        cap = action.capability
        if cap == "file.read":
            path = self._path(action)
            max_bytes = int(action.parameters.get("max_bytes", 1_000_000))
            data = await asyncio.to_thread(path.read_bytes)
            truncated = len(data) > max_bytes
            data = data[:max_bytes]
            return {
                "path": str(path),
                "text": data.decode(action.parameters.get("encoding", "utf-8"), errors="replace"),
                "truncated": truncated,
            }

        if cap == "file.write":
            path = self._path(action)
            content = str(action.parameters.get("content", ""))
            encoding = str(action.parameters.get("encoding", "utf-8"))
            create_parents = bool(action.parameters.get("create_parents", False))
            if create_parents:
                await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_text, content, encoding=encoding)
            return {"path": str(path), "bytes_written": len(content.encode(encoding))}

        if cap == "file.move":
            source = self._path(action)
            destination = Path(str(action.parameters["destination"])).expanduser().resolve(strict=False)
            await asyncio.to_thread(shutil.move, str(source), str(destination))
            return {"source": str(source), "destination": str(destination)}

        if cap == "file.delete":
            path = self._path(action)
            if path.is_dir():
                if not bool(action.parameters.get("recursive", False)):
                    raise IsADirectoryError("recursive=true required to delete a directory")
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(path.unlink)
            return {"path": str(path), "deleted": True}

        if cap == "directory.list":
            path = self._path(action)
            entries = await asyncio.to_thread(lambda: list(path.iterdir()))
            return {
                "path": str(path),
                "entries": [
                    {"name": p.name, "path": str(p), "is_dir": p.is_dir()}
                    for p in entries[: int(action.parameters.get("limit", 500))]
                ],
            }

        if cap == "directory.create":
            path = self._path(action)
            await asyncio.to_thread(
                path.mkdir,
                parents=bool(action.parameters.get("parents", True)),
                exist_ok=bool(action.parameters.get("exist_ok", True)),
            )
            return {"path": str(path), "created": True}

        if cap == "process.list":
            rows: list[dict[str, Any]] = []
            for proc in psutil.process_iter(["pid", "name", "username"]):
                try:
                    rows.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return {"processes": rows[: int(action.parameters.get("limit", 1000))]}

        if cap == "application.launch":
            app = action.parameters.get("application") or (action.target.application if action.target else None)
            if not app:
                raise ValueError("application name/path is required")
            return await asyncio.to_thread(self._launch_app, str(app))

        raise NotImplementedError(cap)

    def _path(self, action: ActionIntent) -> Path:
        raw = action.target.path if action.target else None
        if not raw:
            raise ValueError("target.path is required")
        return Path(raw).expanduser().resolve(strict=False)

    @staticmethod
    def _launch_app(app: str) -> dict[str, Any]:
        system = platform.system().lower()
        if system == "darwin":
            subprocess.Popen(["open", "-a", app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "windows":
            os.startfile(app)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"application": app, "launched": True}
