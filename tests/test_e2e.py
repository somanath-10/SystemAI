from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

from systemai.runtime import build_runtime
from systemai.diagnostics.ports import port_is_listening


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_listening(port):
            return
        time.sleep(0.05)
    raise RuntimeError(f"port {port} did not open")


@pytest.mark.asyncio
async def test_developer_diagnosis_repairs_port_conflict_end_to_end(tmp_path: Path):
    project = tmp_path / "demo-project"
    (project / ".systemai").mkdir(parents=True)
    port = free_port()
    app_py = project / "app.py"
    app_py.write_text(
        f"""
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', {port}), H).serve_forever()
"""
    )
    manifest = {
        "name": "demo-project",
        "runtime": "python",
        "start": [sys.executable, "app.py"],
        "cwd": ".",
        "expected_port": port,
        "health_url": f"http://127.0.0.1:{port}/health",
        "required_env": [],
        "log_files": [],
    }
    (project / ".systemai" / "project.json").write_text(json.dumps(manifest))

    blocker_code = f"import socket,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('127.0.0.1',{port})); s.listen(); time.sleep(60)"
    blocker = subprocess.Popen([sys.executable, "-c", blocker_code], cwd=project)
    target_pid = None
    try:
        wait_port(port)
        runtime = build_runtime(data_dir=tmp_path / "systemai-data", autonomy_mode="standard_auto")
        session = await runtime.create_developer_task("Find why this project is not running and fix it.", project)
        assert session.state.value == "waiting_for_approval"

        # 1) High-risk termination is approved from the canonical kernel action.
        action_id = next(iter(session.pending_approvals))
        runtime.approve(session.task_id, action_id, approved=True, reason="test approves exact blocker termination")
        session = await runtime.run(session.task_id)
        assert session.state.value == "waiting_for_approval"

        # 2) Start command originated in project content, so provenance requires explicit approval.
        action_id = next(iter(session.pending_approvals))
        runtime.approve(session.task_id, action_id, approved=True, reason="test approves declared project start")
        session = await runtime.run(session.task_id)
        assert session.state.value == "completed", session.snapshot()

        start_node = session.graph.nodes["start-project"]
        target_pid = session.results[start_node.action.action_id].output["pid"]
        assert psutil.pid_exists(target_pid)
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        assert r.status_code == 200
        assert runtime.store.verify_chain()
        events = runtime.store.list_events(task_id=session.task_id, limit=500)
        types = [e["event_type"] for e in events]
        assert "ApprovalRequested" in types
        assert "ApprovalGranted" in types
        assert "VerificationPassed" in types
        assert "TaskCompleted" in types
        assert not psutil.pid_exists(blocker.pid)
    finally:
        if blocker.poll() is None:
            blocker.terminate()
            blocker.wait(timeout=3)
        if target_pid and psutil.pid_exists(target_pid):
            try:
                p = psutil.Process(target_pid)
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                pass
