from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from systemai.contracts.desktop import DesktopDriverStatus, DesktopPermissionStatus


class CuaDriverError(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


@dataclass(slots=True)
class CuaCLIConfig:
    binary: str = "cua-driver"
    socket_path: str | None = None
    timeout_seconds: float = 20.0


class CuaCLIClient:
    """Thin, dependency-free proxy to an audited Cua Driver installation.

    On macOS this deliberately talks to the app-owned daemon instead of trying to
    own TCC permissions from Python. That keeps Accessibility/Screen Recording
    attribution attached to CuaDriver.app and leaves SystemAI Core platform-neutral.
    """

    def __init__(self, config: CuaCLIConfig | None = None) -> None:
        self.config = config or CuaCLIConfig()

    @property
    def executable(self) -> str | None:
        raw = self.config.binary
        if Path(raw).is_absolute():
            return raw if Path(raw).exists() else None
        return shutil.which(raw)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        executable = self.executable
        if not executable:
            raise CuaDriverError(
                "cua-driver is not installed or not on PATH; install the audited driver before enabling desktop control",
                code="driver_not_installed",
            )
        argv = [executable, "call", name, json.dumps(arguments, separators=(",", ":"))]
        if self.config.socket_path:
            argv.extend(["--socket", self.config.socket_path])
        completed = await self._run(argv)
        payload = _parse_json_output(completed[0])
        if completed[1] != 0:
            code = _error_code(payload)
            raise CuaDriverError(
                _error_message(payload) or completed[2] or f"cua-driver call failed ({completed[1]})",
                code=code,
                payload=payload,
            )
        if payload.get("is_error") is True or payload.get("isError") is True:
            raise CuaDriverError(
                _error_message(payload) or "cua-driver tool returned an error",
                code=_error_code(payload),
                payload=payload,
            )
        if payload.get("status") == "refused" or payload.get("effect") == "refused":
            raise CuaDriverError(
                _error_message(payload) or "cua-driver refused the action",
                code=_error_code(payload),
                payload=payload,
            )
        return payload

    async def status(self) -> DesktopDriverStatus:
        executable = self.executable
        if not executable:
            return DesktopDriverStatus(configured=True, available=False, backend="cua-cli", details={"reason": "binary_not_found"})

        version_out, version_code, version_err = await self._run([executable, "--version"], raise_timeout=False)
        status_out, status_code, status_err = await self._run([executable, "status"], raise_timeout=False)
        permissions: DesktopPermissionStatus | None = None
        perm_out, perm_code, _ = await self._run(
            [executable, "permissions", "status", "--json"],
            raise_timeout=False,
        )
        if perm_code == 0:
            raw = _parse_json_output(perm_out)
            permissions = DesktopPermissionStatus(
                accessibility=raw.get("accessibility"),
                screen_recording=raw.get("screen_recording") if "screen_recording" in raw else raw.get("screenRecording"),
                direct_capture_status=raw.get("direct_capture_status") or raw.get("directCaptureStatus"),
                source=raw.get("source") or {},
            )

        return DesktopDriverStatus(
            configured=True,
            available=status_code == 0,
            backend="cua-cli",
            version=version_out.strip() if version_code == 0 else None,
            daemon_status=status_out.strip() if status_out else status_err.strip() or None,
            permissions=permissions,
            details={"binary": executable, "status_exit_code": status_code, "version_error": version_err.strip() or None},
        )

    async def doctor(self) -> dict[str, Any]:
        executable = self.executable
        if not executable:
            raise CuaDriverError("cua-driver is not installed", code="driver_not_installed")
        out, code, err = await self._run([executable, "doctor"], raise_timeout=False)
        return {"ok": code == 0, "stdout": out, "stderr": err, "exit_code": code}

    async def _run(self, argv: list[str], *, raise_timeout: bool = True) -> tuple[str, int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.config.timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                if raise_timeout:
                    raise CuaDriverError(
                        f"cua-driver timed out after {self.config.timeout_seconds:.1f}s",
                        code="driver_timeout",
                    )
                return "", 124, "timeout"
            return stdout.decode("utf-8", errors="replace"), int(proc.returncode or 0), stderr.decode("utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise CuaDriverError("cua-driver executable disappeared", code="driver_not_installed") from exc


def _parse_json_output(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        pass

    # Some versions print a small diagnostic line before the JSON payload. Parse
    # the final JSON-looking line without invoking a shell or eval.
    for line in reversed([line.strip() for line in stripped.splitlines() if line.strip()]):
        try:
            parsed = json.loads(line)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        except json.JSONDecodeError:
            continue
    return {"text": stripped}


def _error_code(payload: dict[str, Any]) -> str | None:
    refusal = payload.get("refusal")
    if isinstance(refusal, dict) and refusal.get("code"):
        return str(refusal["code"])
    code = payload.get("error_code") or payload.get("errorCode") or payload.get("code")
    return str(code) if code is not None else None


def _error_message(payload: dict[str, Any]) -> str | None:
    refusal = payload.get("refusal")
    if isinstance(refusal, dict) and refusal.get("message"):
        return str(refusal["message"])
    for key in ("message", "error", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
