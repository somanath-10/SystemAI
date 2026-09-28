from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from time import perf_counter

from systemai.contracts.models import ActionIntent, ActionResult, SandboxProfile
from systemai.execution.authorized import AuthorizedExecutor
from systemai.execution.environment import clean_environment


DEFAULT_ALLOWED_BINARIES = {
    "python", "python3", "pytest", "node", "npm", "pnpm", "yarn", "git", "cargo", "go", "java", "mvn", "gradle",
}


class SandboxExecutorV1(AuthorizedExecutor):
    """V1 bounded command worker.

    It intentionally fails closed for profiles requiring network isolation when no
    enforceable backend (Docker/bwrap/firejail) is available. It never accepts a
    shell command string; argv is executed directly with shell=False semantics.
    """

    CAPABILITIES = {"sandbox.run", "test.run"}

    def __init__(self, *, verifier, event_store=None, allowed_binaries: set[str] | None = None) -> None:
        super().__init__(name="sandbox", verifier=verifier, event_store=event_store)
        self.allowed_binaries = allowed_binaries or DEFAULT_ALLOWED_BINARIES

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        started = perf_counter()
        try:
            argv = action.parameters.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                raise ValueError("sandbox action requires argv: list[str]")
            if any(x in argv[0] for x in [";", "&&", "||", "|", "`", "$("]):
                raise ValueError("shell metacharacters are not accepted; provide argv tokens")
            binary = Path(argv[0]).name
            if binary not in self.allowed_binaries:
                raise PermissionError(f"binary not allowlisted for V1 sandbox: {binary}")
            cwd = Path(str(action.parameters.get("cwd") or (action.target.path if action.target else "."))).expanduser().resolve(strict=True)
            profile = SandboxProfile(str(action.parameters.get("profile", SandboxProfile.READ_ONLY.value)))
            backend = self._backend_for(profile)
            if profile in {SandboxProfile.WORKSPACE_WRITE_NO_NETWORK, SandboxProfile.WORKSPACE_WRITE_ALLOWLIST_NETWORK, SandboxProfile.TEMPORARY_CONTAINER_OR_VM} and backend == "none":
                raise RuntimeError(f"requested sandbox profile '{profile.value}' cannot be enforced on this host; fail closed")
            timeout = float(action.parameters.get("timeout", 120))
            env = clean_environment(action.parameters.get("env", {}))
            command = self._command(backend, profile, cwd, argv)
            proc = await asyncio.create_subprocess_exec(*command, cwd=str(cwd), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f"sandbox command exceeded {timeout}s")
            max_output = int(action.parameters.get("max_output_bytes", 64_000))
            output = {
                "argv": argv,
                "cwd": str(cwd),
                "profile": profile.value,
                "backend": backend,
                "exit_code": proc.returncode,
                "stdout": stdout_b[:max_output].decode(errors="replace"),
                "stderr": stderr_b[:max_output].decode(errors="replace"),
            }
            effect = "confirmed" if proc.returncode == 0 else "failed"
            status = "completed" if proc.returncode == 0 else "failed"
            return ActionResult(action_id=action.action_id, status=status, effect=effect, executor=self.name, output=output, error=None if proc.returncode == 0 else f"command exited {proc.returncode}", duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)

    @staticmethod
    def _backend_for(profile: SandboxProfile) -> str:
        if profile == SandboxProfile.READ_ONLY:
            return "bounded-subprocess"
        if shutil.which("bwrap"):
            return "bwrap"
        if shutil.which("docker"):
            return "docker"
        return "none"

    @staticmethod
    def _command(backend: str, profile: SandboxProfile, cwd: Path, argv: list[str]) -> list[str]:
        if backend == "bwrap":
            # Minimal workspace bind. The source tree is ro for READ_ONLY, rw otherwise.
            bind_flag = "--ro-bind" if profile == SandboxProfile.READ_ONLY else "--bind"
            return ["bwrap", "--die-with-parent", "--proc", "/proc", "--dev", "/dev", bind_flag, str(cwd), str(cwd), "--chdir", str(cwd), *argv]
        if backend == "docker":
            mode = "ro" if profile == SandboxProfile.READ_ONLY else "rw"
            network = "none" if profile == SandboxProfile.WORKSPACE_WRITE_NO_NETWORK else "bridge"
            image = os.environ.get("SYSTEMAI_SANDBOX_IMAGE", "python:3.12-slim")
            return ["docker", "run", "--rm", "--network", network, "-v", f"{cwd}:{cwd}:{mode}", "-w", str(cwd), image, *argv]
        return argv
