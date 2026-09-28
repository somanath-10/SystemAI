from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.execution.authorized import AuthorizedExecutor

MAX_READ_BYTES = 1_000_000
MAX_DIRECTORY_ENTRIES = 5_000


def _bounded_int(value: object, *, default: int, maximum: int, name: str) -> int:
    try:
        result = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= result <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class FileSystemExecutorV1(AuthorizedExecutor):
    CAPABILITIES = {"file.read", "file.write", "file.move", "file.delete", "directory.list", "directory.create"}

    def __init__(self, *, verifier, event_store=None, quarantine_root: Path | None = None) -> None:
        super().__init__(name="filesystem", verifier=verifier, event_store=event_store)
        self.quarantine_root = quarantine_root

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        started = perf_counter()
        try:
            if not action.target or not action.target.path:
                raise ValueError("filesystem action requires target.path")
            path = Path(action.target.path).expanduser().resolve(strict=False)
            out: dict = {"path": str(path)}
            side_effects: list[str] = []
            if action.capability == "file.read":
                max_bytes = _bounded_int(action.parameters.get("max_bytes"), default=512_000, maximum=MAX_READ_BYTES, name="max_bytes")
                size = path.stat().st_size
                with path.open("rb") as handle:
                    data = handle.read(max_bytes)
                out.update({"text": data.decode(action.parameters.get("encoding", "utf-8"), errors="replace"), "size": size, "sha256": sha256_file(path) if size <= MAX_READ_BYTES else None, "truncated": size > len(data)})
            elif action.capability == "directory.list":
                limit = _bounded_int(action.parameters.get("limit"), default=500, maximum=MAX_DIRECTORY_ENTRIES, name="limit")
                entries = []
                for p in sorted(path.iterdir(), key=lambda x: x.name)[:limit]:
                    entries.append({"name": p.name, "path": str(p), "is_dir": p.is_dir(), "size": None if p.is_dir() else p.stat().st_size})
                out["entries"] = entries
            elif action.capability == "directory.create":
                path.mkdir(parents=bool(action.parameters.get("parents", True)), exist_ok=bool(action.parameters.get("exist_ok", True)))
                side_effects.append(f"created directory {path}")
            elif action.capability == "file.write":
                path.parent.mkdir(parents=True, exist_ok=True)
                backup_path = None
                if path.exists() and action.parameters.get("backup", True):
                    backup_path = path.with_name(f".{path.name}.systemai-backup-{uuid4().hex[:8]}")
                    shutil.copy2(path, backup_path)
                if "content" not in action.parameters:
                    raise ValueError("file.write requires parameters.content")
                temporary = path.with_name(f".{path.name}.systemai-write-{uuid4().hex[:8]}")
                try:
                    temporary.write_text(str(action.parameters["content"]), encoding=str(action.parameters.get("encoding", "utf-8")))
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
                out.update({"sha256": sha256_file(path), "backup_path": str(backup_path) if backup_path else None})
                side_effects.append(f"wrote file {path}")
            elif action.capability == "file.move":
                destination = Path(str(action.parameters["destination"])).expanduser().resolve(strict=False)
                if destination.exists():
                    raise FileExistsError(f"destination already exists: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
                out.update({"destination": str(destination), "sha256": sha256_file(destination) if destination.is_file() else None})
                side_effects.append(f"moved {path} -> {destination}")
            elif action.capability == "file.delete":
                mode = str(action.parameters.get("mode", "quarantine"))
                if mode not in {"quarantine", "trash"}:
                    raise ValueError("V1 file.delete only supports quarantine/trash semantics")
                root = self.quarantine_root or path.parent / ".systemai-quarantine"
                root.mkdir(parents=True, exist_ok=True)
                destination = root / f"{path.name}.{uuid4().hex[:8]}"
                shutil.move(str(path), str(destination))
                out["quarantine_path"] = str(destination)
                side_effects.append(f"quarantined {path}")
            return ActionResult(
                action_id=action.action_id,
                status="completed",
                effect="confirmed",
                executor=self.name,
                output=out,
                side_effects=side_effects,
                duration_ms=(perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)
