from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import psutil

from systemai.contracts.models import ActionIntent, ActionResult, VerificationResult, VerificationStatus
from systemai.desktop import DesktopControlService
from systemai.execution.browser import PlaywrightExecutor
from systemai.verification.desktop_probe import DesktopVerificationProbe
from systemai.diagnostics.ports import listening_connections
from systemai.diagnostics.project_inspector import local_health_url


MAX_HASH_BYTES = 100_000_000


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_in_scope(path: Path, action: ActionIntent) -> bool:
    candidate = path.expanduser().resolve(strict=False)
    for scope in action.resource_scope:
        if scope.kind != "filesystem":
            continue
        root = Path(scope.value).expanduser().resolve(strict=False)
        if candidate == root:
            return True
        if scope.recursive:
            try:
                candidate.relative_to(root)
                return True
            except ValueError:
                pass
    return bool(action.target and action.target.path and candidate == Path(action.target.path).expanduser().resolve(strict=False))


class PostconditionVerifier:
    """Independent postcondition verifier for capabilities."""

    def __init__(self, desktop: DesktopControlService | None = None, browser: PlaywrightExecutor | None = None) -> None:
        self.desktop = desktop
        self.desktop_probe = DesktopVerificationProbe(desktop) if desktop else None
        self.browser = browser

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
            if kind == "browser.url_equals":
                page = await self._browser_page()
                expected = str(params["url"])
                return {"kind": kind, "passed": page.url == expected, "actual": page.url, "expected": expected}
            if kind == "browser.title_equals":
                page = await self._browser_page()
                actual = await page.title()
                expected = str(params["title"])
                return {"kind": kind, "passed": actual == expected, "actual": actual, "expected": expected}
            if kind == "browser.text_visible":
                page = await self._browser_page()
                text = str(params["text"])
                passed = await page.get_by_text(text, exact=True).first.is_visible()
                return {"kind": kind, "passed": passed, "text": text}
            if kind == "browser.value_sha256":
                await self._browser_page()
                assert self.browser is not None
                locator = self.browser._locator(action)
                actual = hashlib.sha256((await locator.input_value()).encode()).hexdigest()
                return {"kind": kind, "passed": actual == params["sha256"], "sha256": actual}
            if kind == "browser.download_sha256":
                path = Path(str(result.output.get("path", ""))).expanduser()
                expected = str(result.output.get("sha256", ""))
                actual = _sha256(path) if _file_in_scope(path, action) and path.is_file() and path.stat().st_size <= 50_000_000 else None
                return {"kind": kind, "passed": actual is not None and actual == expected, "path": str(path), "sha256": actual}
            if kind == "browser.upload_selected":
                await self._browser_page()
                assert self.browser is not None
                names = await self.browser._locator(action).evaluate("el => Array.from(el.files || []).map(file => file.name)")
                expected = Path(str(action.parameters["path"])).name
                return {"kind": kind, "passed": names == [expected], "file_names": names}
            if kind == "desktop.apps_observed":
                if self.desktop is None:
                    return {"kind": kind, "passed": False, "error": "desktop verifier unavailable"}
                apps = await self.desktop.list_apps()
                return {"kind": kind, "passed": True, "app_count": len(apps)}
            if kind in {"application.running", "window.exists", "ui.element_exists", "ui.element_value_sha256"}:
                if self.desktop_probe is None:
                    return {"kind": kind, "passed": False, "error": "desktop verifier unavailable"}
                check = {
                    "application.running": self.desktop_probe.application_running,
                    "window.exists": self.desktop_probe.window_exists,
                    "ui.element_exists": self.desktop_probe.element_exists,
                    "ui.element_value_sha256": self.desktop_probe.element_value_sha256,
                }[kind]
                passed, detail = await check(params)
                return {"kind": kind, "passed": passed, "detail": detail}
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
                timeout = float(params.get("timeout", 3))
                if not local_health_url(url) or not 0 < timeout <= 30:
                    return {"kind": kind, "passed": False, "error": "http.health verification requires a loopback URL and a timeout between 0 and 30 seconds"}
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                    async with client.stream("GET", url) as response:
                        passed = int(params.get("min", 200)) <= response.status_code <= int(params.get("max", 399))
                        return {"kind": kind, "passed": passed, "status_code": response.status_code, "url": url}
            if kind == "command.exit_code":
                expected = int(params.get("equals", 0))
                actual = int(result.output.get("exit_code", -999))
                return {"kind": kind, "passed": actual == expected, "actual": actual, "expected": expected}
            if kind == "file.exists":
                path = Path(str(params.get("path") or (action.target.path if action.target else ""))).expanduser()
                if not _file_in_scope(path, action):
                    return {"kind": kind, "passed": False, "error": "file verification is outside action scope"}
                return {"kind": kind, "passed": path.exists(), "path": str(path)}
            if kind == "file.absent":
                path = Path(str(params.get("path") or (action.target.path if action.target else ""))).expanduser()
                if not _file_in_scope(path, action):
                    return {"kind": kind, "passed": False, "error": "file verification is outside action scope"}
                return {"kind": kind, "passed": not path.exists(), "path": str(path)}
            if kind == "file.hash":
                path = Path(str(params["path"])).expanduser()
                if not _file_in_scope(path, action):
                    return {"kind": kind, "passed": False, "error": "file verification is outside action scope"}
                actual = _sha256(path) if path.exists() and path.stat().st_size <= MAX_HASH_BYTES else None
                expected = str(params["sha256"])
                return {"kind": kind, "passed": actual == expected, "actual": actual, "expected": expected}
            return {"kind": kind, "passed": False, "error": "unsupported verification kind"}
        except Exception as exc:
            return {"kind": kind, "passed": False, "error": f"{type(exc).__name__}: {exc}"}

    async def _browser_page(self):
        if self.browser is None:
            raise RuntimeError("browser verifier unavailable")
        return await self.browser.current_page()
