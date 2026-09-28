from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tomllib
from pathlib import Path
from time import perf_counter

import psutil

from systemai.contracts.models import ActionIntent, ActionResult
from systemai.diagnostics.ports import listening_connections
from systemai.diagnostics.project_inspector import project_path
from systemai.execution.authorized import AuthorizedExecutor

MAX_LOG_BYTES = 1_000_000
MAX_LOG_FILES = 100


def _bounded_int(value: object, *, default: int, maximum: int, name: str) -> int:
    try:
        result = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= result <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return result


def _run(argv: list[str], *, cwd: Path | None = None, timeout: float = 5.0) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(argv, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return cp.returncode, cp.stdout, cp.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or str(exc)


def _env_keys(path: Path) -> list[str]:
    keys: list[str] = []
    if not path.exists():
        return keys
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key.replace("_", "").isalnum():
            keys.append(key)
    return sorted(set(keys))


class DiagnosticExecutorV1(AuthorizedExecutor):
    CAPABILITIES = {
        "git.inspect",
        "environment.inspect",
        "package.inspect",
        "log.inspect",
        "port.inspect",
        "network.inspect",
        "service.inspect",
        "container.inspect",
        "database.inspect",
    }

    def __init__(self, *, verifier, event_store=None) -> None:
        super().__init__(name="diagnostic", verifier=verifier, event_store=event_store)

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    async def execute_authorized(self, action: ActionIntent) -> ActionResult:
        started = perf_counter()
        try:
            root = Path((action.target.path if action.target and action.target.path else action.parameters.get("project_root", "."))).expanduser().resolve(strict=False)
            if action.capability == "git.inspect":
                output = self._git(root)
            elif action.capability == "environment.inspect":
                output = self._env(root, action)
            elif action.capability == "package.inspect":
                output = self._packages(root)
            elif action.capability == "log.inspect":
                output = self._logs(root, action)
            elif action.capability == "port.inspect":
                output = self._ports(action)
            elif action.capability == "network.inspect":
                output = self._network()
            elif action.capability == "service.inspect":
                output = self._service(action)
            elif action.capability == "container.inspect":
                output = self._containers(root)
            elif action.capability == "database.inspect":
                output = self._database(action)
            else:
                raise ValueError(action.capability)
            return ActionResult(action_id=action.action_id, status="completed", effect="confirmed", executor=self.name, output=output, duration_ms=(perf_counter()-started)*1000)
        except Exception as exc:
            return ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=self.name, error=f"{type(exc).__name__}: {exc}", duration_ms=(perf_counter()-started)*1000)

    def _git(self, root: Path) -> dict:
        if not (root / ".git").exists():
            return {"is_git": False}
        commands = {
            "branch": ["git", "branch", "--show-current"],
            "status": ["git", "status", "--porcelain=v1"],
            "recent": ["git", "log", "-5", "--pretty=format:%h%x09%ad%x09%s", "--date=iso-strict"],
            "diff_stat": ["git", "diff", "--stat"],
        }
        out: dict = {"is_git": True}
        for key, argv in commands.items():
            code, stdout, stderr = _run(argv, cwd=root)
            out[key] = stdout[:20_000]
            if code != 0:
                out[f"{key}_error"] = stderr[:4000]
        return out

    def _env(self, root: Path, action: ActionIntent) -> dict:
        template_name = str(action.parameters.get("template", ".env.example"))
        env_name = str(action.parameters.get("env_file", ".env"))
        template = project_path(root, template_name)
        env_file = project_path(root, env_name)
        expected = _env_keys(template)
        actual = _env_keys(env_file)
        declared = [str(x) for x in action.parameters.get("required_env", [])]
        required = sorted(set(expected + declared))
        missing = sorted(set(required) - set(actual) - set(os.environ.keys()))
        return {
            "template_exists": template.exists(),
            "env_file_exists": env_file.exists(),
            "required_keys": required,
            "present_keys": sorted(set(actual) | (set(required) & set(os.environ.keys()))),
            "missing_keys": missing,
            "values_exposed": False,
        }

    def _packages(self, root: Path) -> dict:
        out: dict = {"root": str(root), "manifests": [], "runtime_hints": []}
        package_json = root / "package.json"
        if package_json.exists():
            data = json.loads(package_json.read_text(errors="replace"))
            out["manifests"].append("package.json")
            out["runtime_hints"].append("node")
            out["node"] = {
                "scripts": data.get("scripts", {}),
                "dependencies": sorted((data.get("dependencies") or {}).keys()),
                "devDependencies": sorted((data.get("devDependencies") or {}).keys()),
                "node_modules_exists": (root / "node_modules").exists(),
                "lock_files": [x.name for x in (root / "package-lock.json", root / "pnpm-lock.yaml", root / "yarn.lock") if x.exists()],
            }
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            data = tomllib.loads(pyproject.read_text(errors="replace"))
            out["manifests"].append("pyproject.toml")
            out["runtime_hints"].append("python")
            project = data.get("project", {})
            out["python"] = {
                "name": project.get("name"),
                "requires_python": project.get("requires-python"),
                "dependencies": project.get("dependencies", []),
                "venv_exists": any((root / x).exists() for x in (".venv", "venv")),
            }
        req = root / "requirements.txt"
        if req.exists():
            out["manifests"].append("requirements.txt")
            out["runtime_hints"].append("python")
            out["requirements_count"] = len([x for x in req.read_text(errors="replace").splitlines() if x.strip() and not x.strip().startswith("#")])
        for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            if (root / name).exists():
                out["manifests"].append(name)
                out["runtime_hints"].append("containers")
        out["runtime_hints"] = sorted(set(out["runtime_hints"]))
        return out

    def _logs(self, root: Path, action: ActionIntent) -> dict:
        paths = [Path(x) for x in action.parameters.get("log_files", [])]
        if not paths:
            paths = list(root.glob("*.log")) + list((root / "logs").glob("*.log")) if (root / "logs").exists() else list(root.glob("*.log"))
        max_files = _bounded_int(action.parameters.get("max_files"), default=10, maximum=MAX_LOG_FILES, name="max_files")
        max_bytes = _bounded_int(action.parameters.get("max_bytes_per_file"), default=16_000, maximum=MAX_LOG_BYTES, name="max_bytes_per_file")
        logs = []
        for item in paths[:max_files]:
            p = project_path(root, item)
            if not p.exists() or not p.is_file():
                continue
            size = p.stat().st_size
            with p.open("rb") as handle:
                handle.seek(max(0, size - max_bytes))
                tail = handle.read(max_bytes).decode(errors="replace")
            logs.append({"path": str(p), "size": size, "tail": tail})
        return {"logs": logs}

    def _ports(self, action: ActionIntent) -> dict:
        wanted = action.target.port if action.target else None
        if wanted is None:
            wanted = action.parameters.get("port")
        listeners = []
        for conn in listening_connections(int(wanted) if wanted is not None else None):
            port = conn.laddr.port
            item = {"ip": conn.laddr.ip, "port": port, "pid": conn.pid}
            if conn.pid:
                try:
                    p = psutil.Process(conn.pid)
                    item.update({"process_name": p.name(), "cmdline": p.cmdline(), "create_time": p.create_time()})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            listeners.append(item)
        return {"requested_port": int(wanted) if wanted is not None else None, "listeners": listeners}

    def _network(self) -> dict:
        addrs = {}
        for name, values in psutil.net_if_addrs().items():
            addrs[name] = [{"family": str(x.family), "address": x.address, "netmask": x.netmask} for x in values]
        return {"interfaces": addrs}

    def _service(self, action: ActionIntent) -> dict:
        name = (action.target.service_name if action.target else None) or action.parameters.get("service_name")
        if not name:
            return {"supported": False, "reason": "no service_name supplied"}
        if shutil.which("systemctl"):
            code, stdout, stderr = _run(["systemctl", "is-active", str(name)], timeout=4)
            return {"supported": True, "service": name, "active": code == 0 and stdout.strip() == "active", "raw": stdout.strip(), "error": stderr.strip()}
        return {"supported": False, "service": name, "reason": "systemctl unavailable; platform adapter required"}

    def _containers(self, root: Path) -> dict:
        runtime = shutil.which("docker") or shutil.which("podman")
        if not runtime:
            return {"runtime_available": False, "compose_files": [p.name for p in root.glob("*compose*.y*ml")]}
        code, stdout, stderr = _run([runtime, "ps", "--format", "{{json .}}"], timeout=5)
        rows = []
        if code == 0:
            for line in stdout.splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    rows.append({"raw": line})
        return {"runtime_available": True, "runtime": runtime, "containers": rows, "error": stderr[:4000]}

    def _database(self, action: ActionIntent) -> dict:
        host = str(action.parameters.get("host", "127.0.0.1"))
        port = action.parameters.get("port") or (action.target.port if action.target else None)
        if port is None:
            return {"reachable": False, "reason": "database.inspect requires a port or a specific adapter"}
        timeout = float(action.parameters.get("timeout", 1.0))
        if not 0 < timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds")
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                pass
            return {"host": host, "port": int(port), "reachable": True, "mode": "tcp-health-only"}
        except OSError:
            return {"host": host, "port": int(port), "reachable": False, "mode": "tcp-health-only"}
