from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import psutil

from systemai.contracts.models import ActionIntent, ActionResult, VerificationResult, VerificationStatus
from systemai.diagnostics.ports import listening_connections


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class VerifierV1:
    """Independent postcondition verifier for V1 capabilities."""

    async def verify(self, action: ActionIntent, result: ActionResult) -> VerificationResult:
        checks: list[dict] = []
        if result.status.value not in {"completed", "allowed"}:
            return VerificationResult(action_id=action.action_id, status=VerificationStatus.FAILED, checks=[{"kind": "executor_result", "passed": False, "error": result.error}], summary="Executor did not complete the action.")
        specs = action.verification
        if not specs:
            passed = result.effect.value == "confirmed"
            return VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED if passed else VerificationStatus.UNKNOWN, checks=[{"kind": "effect", "passed": passed, "effect": result.effect.value}], summary="No explicit verifier supplied; executor effect was used only as a fallback signal.")
        overall = True
        for spec in specs:
            check = await self._check(spec.kind, spec.parameters, action, result)
            checks.append(check)
            if spec.required and not check.get("passed", False):
                overall = False
        return VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED if overall else VerificationStatus.FAILED, checks=checks, summary="All required postconditions passed." if overall else "One or more required postconditions failed.")

    async def _check(self, kind: str, params: dict, action: ActionIntent, result: ActionResult) -> dict:
        try:
            if kind == "process.absent":
                pid = int(params["pid"])
                passed = not psutil.pid_exists(pid)
                return {"kind": kind, "passed": passed, "pid": pid}
            if kind == "process.alive":
                pid = int(params["pid"])
                passed = psutil.pid_exists(pid) and psutil.Process(pid).is_running()
                return {"kind": kind, "passed": passed, "pid": pid}
            if kind == "process.started_from_result":
                pid = int(result.output.get("pid", -1))
                passed = pid > 0 and psutil.pid_exists(pid)
                return {"kind": kind, "passed": passed, "pid": pid}
            if kind == "port.listening":
                port = int(params["port"])
                timeout = float(params.get("timeout", 5.0))
                deadline = asyncio.get_running_loop().time() + timeout
                while True:
                    listeners = listening_connections(port)
                    if listeners:
                        return {"kind": kind, "passed": True, "port": port, "pids": [c.pid for c in listeners]}
                    if asyncio.get_running_loop().time() >= deadline:
                        return {"kind": kind, "passed": False, "port": port}
                    await asyncio.sleep(0.1)
            if kind == "http.status":
                code = int(result.output.get("status_code", 0))
                lo, hi = int(params.get("min", 200)), int(params.get("max", 399))
                return {"kind": kind, "passed": lo <= code <= hi, "status_code": code, "expected": [lo, hi]}
            if kind == "http.health":
                url = str(params["url"])
                async with httpx.AsyncClient(timeout=float(params.get("timeout", 3))) as client:
                    r = await client.get(url)
                passed = int(params.get("min", 200)) <= r.status_code <= int(params.get("max", 399))
                return {"kind": kind, "passed": passed, "status_code": r.status_code, "url": url}
            if kind == "command.exit_code":
                expected = int(params.get("equals", 0))
                actual = int(result.output.get("exit_code", -999))
                return {"kind": kind, "passed": actual == expected, "actual": actual, "expected": expected}
            if kind == "file.exists":
                path = Path(str(params.get("path") or (action.target.path if action.target else ""))).expanduser()
                return {"kind": kind, "passed": path.exists(), "path": str(path)}
            if kind == "file.absent":
                path = Path(str(params.get("path") or (action.target.path if action.target else ""))).expanduser()
                return {"kind": kind, "passed": not path.exists(), "path": str(path)}
            if kind == "file.hash":
                path = Path(str(params["path"])).expanduser()
                actual = _sha256(path) if path.exists() else None
                expected = str(params["sha256"])
                return {"kind": kind, "passed": actual == expected, "actual": actual, "expected": expected}
            return {"kind": kind, "passed": False, "error": "unsupported verification kind"}
        except Exception as exc:
            return {"kind": kind, "passed": False, "error": f"{type(exc).__name__}: {exc}"}
