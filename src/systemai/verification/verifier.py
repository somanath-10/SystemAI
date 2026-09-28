from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import psutil

from systemai.contracts.models import (
    ActionIntent,
    ActionResult,
    EffectStatus,
    VerificationResult,
    VerificationStatus,
)


class Verifier:
    """Independent postcondition checker.

    Execution success is not task success. A result is trusted only when required
    postconditions are independently observed. Desktop checks use a fresh driver
    observation rather than trusting the action result.
    """

    def __init__(self, desktop_probe=None) -> None:
        self.desktop_probe = desktop_probe

    async def verify(self, action: ActionIntent, result: ActionResult) -> VerificationResult:
        if result.effect == EffectStatus.FAILED:
            return VerificationResult(
                action_id=action.action_id,
                status=VerificationStatus.FAILED,
                summary=result.error or "executor reported failure",
            )

        if not action.verification:
            status = (
                VerificationStatus.PASSED
                if result.effect == EffectStatus.CONFIRMED
                else VerificationStatus.UNKNOWN
            )
            return VerificationResult(
                action_id=action.action_id,
                status=status,
                summary="No explicit verifier configured; used executor effect status.",
            )

        checks: list[dict[str, Any]] = []
        all_required_passed = True
        any_unknown = False

        for spec in action.verification:
            try:
                passed, detail = await self._check(spec.kind, spec.parameters, result)
                checks.append({"kind": spec.kind, "passed": passed, "detail": detail, "required": spec.required})
                if spec.required and not passed:
                    all_required_passed = False
            except Exception as exc:
                checks.append({"kind": spec.kind, "passed": None, "detail": f"{type(exc).__name__}: {exc}", "required": spec.required})
                any_unknown = True
                if spec.required:
                    all_required_passed = False

        if all_required_passed:
            status = VerificationStatus.PASSED
        elif any_unknown and not any(c.get("passed") is False and c.get("required") for c in checks):
            status = VerificationStatus.UNKNOWN
        else:
            status = VerificationStatus.FAILED

        return VerificationResult(
            action_id=action.action_id,
            status=status,
            checks=checks,
            summary=f"{sum(1 for c in checks if c.get('passed') is True)}/{len(checks)} checks passed",
        )

    async def _check(self, kind: str, params: dict[str, Any], result: ActionResult) -> tuple[bool, Any]:
        if kind == "file.exists":
            path = Path(str(params["path"])).expanduser()
            return path.exists(), str(path)

        if kind == "file.not_exists":
            path = Path(str(params["path"])).expanduser()
            return not path.exists(), str(path)

        if kind == "file.content_equals":
            path = Path(str(params["path"])).expanduser()
            expected = str(params["content"])
            actual = path.read_text(encoding=str(params.get("encoding", "utf-8")))
            return actual == expected, {"path": str(path), "actual_length": len(actual)}

        if kind == "file.sha256":
            path = Path(str(params["path"])).expanduser()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest == str(params["sha256"]), {"path": str(path), "sha256": digest}

        if kind == "process.running":
            name = str(params["name"]).lower()
            matches = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if name in (proc.info.get("name") or "").lower():
                        matches.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return bool(matches), matches[:10]

        if kind == "application.running":
            if self.desktop_probe is None:
                raise RuntimeError("desktop verification probe is not configured")
            return await self.desktop_probe.application_running(params)

        if kind == "window.exists":
            if self.desktop_probe is None:
                raise RuntimeError("desktop verification probe is not configured")
            return await self.desktop_probe.window_exists(params)

        if kind == "ui.element_exists":
            if self.desktop_probe is None:
                raise RuntimeError("desktop verification probe is not configured")
            return await self.desktop_probe.element_exists(params)

        if kind == "ui.element_value_equals":
            if self.desktop_probe is None:
                raise RuntimeError("desktop verification probe is not configured")
            return await self.desktop_probe.element_value_equals(params)

        if kind == "result.field_equals":
            field = str(params["field"])
            expected = params.get("value")
            actual = result.output.get(field)
            return actual == expected, {"field": field, "actual": actual, "expected": expected}

        if kind == "result.field_truthy":
            field = str(params["field"])
            actual = result.output.get(field)
            return bool(actual), {"field": field, "actual": actual}

        raise ValueError(f"unknown verification kind: {kind}")
