from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psutil
from pydantic import ValidationError

from systemai.contracts.models import ProjectManifest
from systemai.diagnostics.ports import listening_connections


def _run(argv: list[str], cwd: Path, timeout: float = 5.0) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
        return cp.returncode, cp.stdout, cp.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or str(exc)


def _env_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    keys: list[str] = []
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key.replace("_", "").isalnum():
            keys.append(key)
    return sorted(set(keys))


def project_path(root: Path, value: str | Path) -> Path:
    """Resolve a manifest path and reject attempts to leave the declared project."""
    candidate = Path(value).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path is outside project root: {value}") from exc
    return resolved


def local_health_url(url: str | None) -> bool:
    if not url:
        return True
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "::1", "localhost"}


class ProjectInspector:
    """Read-only observation plane for the developer diagnosis wedge."""

    def load_manifest(self, root: Path) -> ProjectManifest:
        candidates = [root / ".systemai" / "project.json", root / "systemai.project.json"]
        for path in candidates:
            if path.exists():
                path = project_path(root, path)
                data = json.loads(path.read_text())
                return ProjectManifest.model_validate(data)
        # conservative auto-detection; never guesses destructive repair steps
        runtime = None
        start: list[str] = []
        test: list[str] = []
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            runtime = "python"
        if (root / "package.json").exists():
            runtime = "node"
            try:
                p = json.loads((root / "package.json").read_text())
                scripts = p.get("scripts", {})
                if "test" in scripts:
                    test = ["npm", "test", "--", "--runInBand"]
                if "start" in scripts:
                    start = ["npm", "start"]
                elif "dev" in scripts:
                    start = ["npm", "run", "dev"]
            except Exception:
                pass
        return ProjectManifest(name=root.name, runtime=runtime, start=start, test=test)

    def _manifest(self, root: Path) -> tuple[ProjectManifest, str | None]:
        try:
            return self.load_manifest(root), None
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return ProjectManifest(name=root.name), f"{type(exc).__name__}: {exc}"

    def inspect(self, root: Path) -> dict[str, Any]:
        root = root.expanduser().resolve(strict=True)
        manifest, manifest_error = self._manifest(root)
        facts: dict[str, Any] = {
            "project_root": str(root),
            "manifest": manifest.model_dump(mode="json"),
            "exists": root.exists(),
            "runtime": manifest.runtime,
            "git": self._git(root),
            "env": self._env(root, manifest),
            "packages": self._packages(root),
            "port": self._port(manifest.expected_port),
            "health": self._health(manifest.health_url),
            "logs": self._logs(root, manifest.log_files),
            "manifest_issues": self._manifest_issues(root, manifest),
        }
        if manifest_error:
            facts["manifest_error"] = manifest_error
        return facts

    def _git(self, root: Path) -> dict[str, Any]:
        if not (root / ".git").exists():
            return {"is_git": False}
        code, branch, _ = _run(["git", "branch", "--show-current"], root)
        _, status, _ = _run(["git", "status", "--porcelain=v1"], root)
        _, recent, _ = _run(["git", "log", "-5", "--pretty=format:%h%x09%ad%x09%s", "--date=iso-strict"], root)
        return {"is_git": code == 0, "branch": branch.strip(), "status": status[:20_000], "recent": recent[:20_000]}

    def _env(self, root: Path, manifest: ProjectManifest) -> dict[str, Any]:
        expected = sorted(set(_env_keys(root / ".env.example") + list(manifest.required_env)))
        actual = set(_env_keys(root / ".env")) | set(os.environ)
        missing = [k for k in expected if k not in actual]
        return {"required_keys": expected, "missing_keys": missing, "values_exposed": False, "env_file_exists": (root / ".env").exists()}

    def _packages(self, root: Path) -> dict[str, Any]:
        return {
            "pyproject": (root / "pyproject.toml").exists(),
            "requirements": (root / "requirements.txt").exists(),
            "package_json": (root / "package.json").exists(),
            "node_modules": (root / "node_modules").exists(),
            "venv": (root / ".venv").exists() or (root / "venv").exists(),
            "docker_compose": any((root / x).exists() for x in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        }

    def _port(self, port: int | None) -> dict[str, Any]:
        if port is None:
            return {"expected_port": None, "listeners": []}
        listeners: list[dict[str, Any]] = []
        for conn in listening_connections(port):
            item: dict[str, Any] = {"port": port, "pid": conn.pid, "ip": conn.laddr.ip}
            if conn.pid:
                try:
                    p = psutil.Process(conn.pid)
                    item.update({"name": p.name(), "cmdline": p.cmdline(), "cwd": p.cwd(), "create_time": p.create_time()})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            listeners.append(item)
        return {"expected_port": port, "listeners": listeners}

    def _health(self, url: str | None) -> dict[str, Any]:
        if not url:
            return {"url": None, "reachable": None}
        if not local_health_url(url):
            return {"url": url, "reachable": False, "ok": False, "error": "health_url must use a loopback HTTP(S) address"}
        try:
            with httpx.stream("GET", url, timeout=1.5, follow_redirects=False) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk[: 2000 - len(body)])
                    if len(body) == 2000:
                        break
                return {"url": url, "reachable": True, "status_code": response.status_code, "ok": 200 <= response.status_code < 400, "body": bytes(body).decode(errors="replace")}
        except Exception as exc:
            return {"url": url, "reachable": False, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _logs(self, root: Path, declared: list[str]) -> list[dict[str, Any]]:
        paths: list[Path] = []
        for item in declared:
            try:
                paths.append(project_path(root, item))
            except ValueError:
                continue
        if not paths:
            paths.extend(root.glob("*.log"))
            if (root / "logs").exists():
                paths.extend((root / "logs").glob("*.log"))
        out = []
        for item in paths[:10]:
            try:
                p = project_path(root, item)
                if not p.exists() or not p.is_file():
                    continue
                size = p.stat().st_size
                with p.open("rb") as handle:
                    handle.seek(max(0, size - 16_000))
                    tail = handle.read(16_000)
                out.append({"path": str(p), "tail": tail.decode(errors="replace"), "size": size})
            except OSError:
                continue
        return out

    @staticmethod
    def _manifest_issues(root: Path, manifest: ProjectManifest) -> list[str]:
        issues: list[str] = []
        try:
            project_path(root, manifest.cwd)
        except ValueError as exc:
            issues.append(str(exc))
        if not local_health_url(manifest.health_url):
            issues.append("health_url must use a loopback HTTP(S) address")
        for log_file in manifest.log_files:
            try:
                project_path(root, log_file)
            except ValueError as exc:
                issues.append(str(exc))
        return issues
