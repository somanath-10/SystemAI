from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psutil

from systemai.contracts.models import ProjectManifest
from systemai.diagnostics.ports import listening_connections


def _run(argv: list[str], cwd: Path, timeout: float = 5.0) -> tuple[int, str, str]:
    cp = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
    return cp.returncode, cp.stdout, cp.stderr


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
    """Read-only observation plane for the V1 developer diagnosis wedge."""

    def load_manifest(self, root: Path) -> ProjectManifest:
        candidates = [root / ".systemai" / "project.json", root / "systemai.project.json"]
        for path in candidates:
            if path.exists():
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

    def inspect(self, root: Path) -> dict[str, Any]:
        root = root.expanduser().resolve(strict=True)
        manifest = self.load_manifest(root)
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
            r = httpx.get(url, timeout=1.5, follow_redirects=False)
            return {"url": url, "reachable": True, "status_code": r.status_code, "ok": 200 <= r.status_code < 400, "body": r.text[:2000]}
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
        for p in paths[:10]:
            if p.exists() and p.is_file():
                b = p.read_bytes()
                out.append({"path": str(p), "tail": b[-16000:].decode(errors="replace"), "size": len(b)})
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
