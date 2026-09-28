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
MAX_TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_BYTES = 1_000_000


def _bounded_float(value: object, *, default: float, maximum: float, name: str) -> float:
    try:
        result = float(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 0 < result <= maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return result


def _bounded_int(value: object, *, default: int, maximum: int, name: str) -> int:
    try:
        result = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= result <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return result


async def _read_limited(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    output = bytearray()
    truncated = False
    while chunk := await stream.read(65_536):
        remaining = limit - len(output)
        output.extend(chunk[:remaining])
        truncated |= len(chunk) > remaining
    return bytes(output), truncated


class SandboxExecutor(AuthorizedExecutor):
    """Bounded command worker.

    It fails closed whenever an isolated Docker backend is unavailable.
    It never accepts a
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
                raise PermissionError(f"binary not allowlisted for sandbox: {binary}")
            cwd = Path(str(action.parameters.get("cwd") or (action.target.path if action.target else "."))).expanduser().resolve(strict=True)
            profile = SandboxProfile(str(action.parameters.get("profile", SandboxProfile.READ_ONLY.value)))
            backend = self._backend_for(profile)
            if profile in {SandboxProfile.WORKSPACE_WRITE_ALLOWLIST_NETWORK, SandboxProfile.APPROVED_ELEVATED_HOST_OPERATION}:
                raise RuntimeError(f"cannot enforce sandbox profile '{profile.value}'")
            if backend == "none":
                raise RuntimeError(f"requested sandbox profile '{profile.value}' cannot be enforced on this host; fail closed")
            timeout = _bounded_float(action.parameters.get("timeout"), default=120, maximum=MAX_TIMEOUT_SECONDS, name="timeout")
            max_output = _bounded_int(action.parameters.get("max_output_bytes"), default=64_000, maximum=MAX_OUTPUT_BYTES, name="max_output_bytes")
            env = clean_environment(action.parameters.get("env", {}))
            command = self._command(backend, profile, cwd, argv)
            proc = await asyncio.create_subprocess_exec(*command, cwd=str(cwd), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout_task = asyncio.create_task(_read_limited(proc.stdout, max_output))
            stderr_task = asyncio.create_task(_read_limited(proc.stderr, max_output))
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                await asyncio.gather(stdout_task, stderr_task)
                raise TimeoutError(f"sandbox command exceeded {timeout}s") from exc
            except BaseException:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                await asyncio.gather(stdout_task, stderr_task)
                raise
            stdout_b, stdout_truncated = await stdout_task
            stderr_b, stderr_truncated = await stderr_task
            output = {
                "argv": argv,
                "cwd": str(cwd),
                "profile": profile.value,
                "backend": backend,
                "exit_code": proc.returncode,
                "stdout": stdout_b[:max_output].decode(errors="replace"),
                "stderr": stderr_b[:max_output].decode(errors="replace"),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
            effect = "confirmed" if proc.returncode == 0 else "failed"
            status = "completed" if proc.returncode == 0 else "failed"
            return ActionResult(action_id=action.action_id, status=status, effect=effect, executor=self.name, output=output, error=None if proc.returncode == 0 else f"command exited {proc.returncode}", duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)

    @staticmethod
    def _backend_for(profile: SandboxProfile) -> str:
        if shutil.which("docker"):
            return "docker"
        return "none"

    @staticmethod
    def _command(backend: str, profile: SandboxProfile, cwd: Path, argv: list[str]) -> list[str]:
        if backend == "docker":
            mode = "ro" if profile == SandboxProfile.READ_ONLY else "rw"
            image = os.environ.get("SYSTEMAI_SANDBOX_IMAGE", "python:3.12-slim")
            return ["docker", "run", "--rm", "--network", "none", "-v", f"{cwd}:{cwd}:{mode}", "-w", str(cwd), image, *argv]
        return argv
