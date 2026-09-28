from __future__ import annotations

import asyncio
import signal
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter

import psutil

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.execution.authorized import AuthorizedExecutor
from systemai.execution.environment import clean_environment


class ProcessExecutorV1(AuthorizedExecutor):
    CAPABILITIES = {"process.list", "process.inspect", "process.start", "process.terminate"}

    def __init__(self, *, verifier, event_store=None) -> None:
        super().__init__(name="process", verifier=verifier, event_store=event_store)
        self.started_processes: dict[int, asyncio.subprocess.Process] = {}

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        started = perf_counter()
        try:
            if action.capability == "process.list":
                limit = int(action.parameters.get("limit", 500))
                if not 1 <= limit <= 5_000:
                    raise ValueError("limit must be between 1 and 5000")
                items = []
                for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd", "username"]):
                    try:
                        items.append(proc.info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                    if len(items) >= limit:
                        break
                output = {"processes": items}
            elif action.capability == "process.inspect":
                pid = self._pid(action)
                p = psutil.Process(pid)
                with p.oneshot():
                    output = {"pid": pid, "name": p.name(), "cmdline": p.cmdline(), "cwd": p.cwd(), "status": p.status(), "create_time": p.create_time()}
            elif action.capability == "process.start":
                argv = action.parameters.get("argv")
                if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
                    raise ValueError("process.start requires parameters.argv list")
                cwd = Path(str(action.parameters.get("cwd") or (action.target.path if action.target else "."))).expanduser().resolve(strict=True)
                if not cwd.is_dir():
                    raise NotADirectoryError(cwd)
                env = clean_environment(action.parameters.get("env", {}))
                stdout_path = action.parameters.get("stdout_path")
                stderr_path = action.parameters.get("stderr_path")
                with ExitStack() as streams:
                    def output_stream(value):
                        if not value:
                            return asyncio.subprocess.DEVNULL
                        path = Path(str(value)).expanduser().resolve(strict=False)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        return streams.enter_context(path.open("ab", buffering=0))

                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        cwd=str(cwd),
                        env=env,
                        stdout=output_stream(stdout_path),
                        stderr=output_stream(stderr_path),
                        start_new_session=True,
                    )
                self.started_processes[proc.pid] = proc
                output = {"pid": proc.pid, "argv": argv, "cwd": str(cwd)}
            elif action.capability == "process.terminate":
                pid = self._pid(action)
                p = psutil.Process(pid)
                expected_create_time = action.parameters.get("expected_create_time")
                if expected_create_time is not None and abs(p.create_time() - float(expected_create_time)) > 0.001:
                    raise RuntimeError("PID was reused; refusing to terminate a different process")
                sig = signal.SIGTERM
                p.send_signal(sig)
                timeout = float(action.parameters.get("timeout", 5))
                if not 0 < timeout <= 30:
                    raise ValueError("timeout must be between 0 and 30 seconds")
                try:
                    await asyncio.to_thread(p.wait, timeout=timeout)
                except psutil.TimeoutExpired:
                    if not action.parameters.get("allow_kill", False):
                        raise RuntimeError("process did not exit after SIGTERM; kill not authorized")
                    p.kill()
                    await asyncio.to_thread(p.wait, timeout=3)
                output = {"pid": pid, "terminated": True}
            else:
                raise ValueError(action.capability)
            return ActionResult(action_id=action.action_id, status="completed", effect="confirmed", executor=self.name, output=output, duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)

    @staticmethod
    def _pid(action: ActionIntent) -> int:
        pid = action.target.process_id if action.target else None
        if pid is None:
            pid = action.parameters.get("pid")
        if pid is None:
            raise ValueError("process action requires pid")
        return int(pid)
