from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from uuid import uuid4

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.execution.authorized import AuthorizedExecutor
from systemai.execution.cua import CuaDesktopExecutor
from systemai.security.ephemeral import EphemeralValues


class AuthorizedCuaExecutor(AuthorizedExecutor):
    """Run the existing desktop adapter only after signed, single-use authorization."""

    def __init__(self, client, *, verifier, event_store=None, session: str = "systemai", artifact_dir: Path | None = None) -> None:
        super().__init__(name="computer", verifier=verifier, event_store=event_store)
        self.desktop_executor = CuaDesktopExecutor(client, session=session)
        self.values = EphemeralValues()
        self.artifact_dir = artifact_dir

    def stash_value(self, value: str) -> str:
        return self.values.stash(value)

    def forget_value(self, reference: str) -> None:
        self.values.forget(reference)

    def supports(self, capability: str) -> bool:
        return self.desktop_executor.supports(capability)

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        adapted = action
        private_value: str | None = None
        if action.capability == "ui.set_value":
            private_value = self.values.consume(str(action.parameters.get("value_ref", "")))
            adapted = action.model_copy(deep=True)
            adapted.parameters.pop("value_ref", None)
            adapted.parameters.pop("value_sha256", None)
            adapted.parameters["value"] = private_value
        result = await self.desktop_executor.execute(adapted)
        output = self._sanitize(result.output, action.action_id, private_value)
        error = result.error.replace(private_value, "[redacted]") if result.error and private_value else result.error
        return result.model_copy(update={"executor": self.name, "output": output, "error": error})

    def _sanitize(self, value, action_id: str, private_value: str | None):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in {"tree_markdown", "raw", "structured_json"}:
                    continue
                if key in {"value", "text"}:
                    out[key] = "[redacted]"
                    continue
                if key == "screenshot_png_b64":
                    if isinstance(item, str) and self.artifact_dir is not None:
                        try:
                            image = base64.b64decode(item, validate=True)
                            if len(image) > 12_000_000 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
                                raise ValueError("desktop screenshot is not a bounded PNG")
                            self.artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                            path = self.artifact_dir / f"{action_id}-{uuid4().hex}.png"
                            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                            with os.fdopen(fd, "wb") as file:
                                file.write(image)
                            out["screenshot_artifact"] = str(path)
                            out["screenshot_bytes"] = len(image)
                        except (ValueError, binascii.Error, OSError):
                            out["screenshot_discarded"] = True
                    continue
                out[key] = self._sanitize(item, action_id, private_value)
            return out
        if isinstance(value, list):
            return [self._sanitize(item, action_id, private_value) for item in value]
        if isinstance(value, str) and private_value:
            return value.replace(private_value, "[redacted]")
        return value
