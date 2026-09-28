from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import psutil

from systemai.runtime import build_runtime
from systemai.diagnostics.ports import port_is_listening


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port: int, timeout: float = 5) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if port_is_listening(port):
            return
        time.sleep(0.05)
    raise RuntimeError("fixture port did not open")


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="systemai-acceptance-") as td:
        root = Path(td)
        project = root / "project"
        (project / ".systemai").mkdir(parents=True)
        port = free_port()
        (project / "app.py").write_text(
            f"from http.server import BaseHTTPRequestHandler,HTTPServer\n"
            f"class H(BaseHTTPRequestHandler):\n"
            f"  def do_GET(self):\n"
            f"    self.send_response(200 if self.path=='/health' else 404); self.end_headers(); self.wfile.write(b'ok')\n"
            f"  def log_message(self,*a): pass\n"
            f"HTTPServer(('127.0.0.1',{port}),H).serve_forever()\n"
        )
        (project / ".systemai" / "project.json").write_text(json.dumps({
            "name":"acceptance-app","runtime":"python","start":[sys.executable,"app.py"],"cwd":".",
            "expected_port":port,"health_url":f"http://127.0.0.1:{port}/health","required_env":[],"log_files":[]
        }))
        blocker = subprocess.Popen([sys.executable, "-c", f"import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',{port}));s.listen();time.sleep(60)"], cwd=project)
        target_pid = None
        try:
            wait_port(port)
            runtime = build_runtime(data_dir=root / "runtime", autonomy_mode="standard_auto")
            session = await runtime.create_developer_task("Find why this project is not running and fix it.", project)
            approvals = 0
            while session.state.value == "waiting_for_approval":
                action_id, approval_id = next(iter(session.pending_approvals.items()))
                record = runtime.security_kernel.approvals.get(approval_id)
                print("\n[controlled fixture approval]\n" + record["canonical_summary"])
                runtime.approve(session.task_id, action_id, approved=True, reason="controlled acceptance fixture")
                approvals += 1
                session = await runtime.run(session.task_id)
            assert session.state.value == "completed", session.snapshot()
            start = session.graph.nodes["start-project"]
            target_pid = session.results[start.action.action_id].output["pid"]
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
            assert response.status_code == 200
            assert runtime.store.verify_chain()
            print(json.dumps({
                "status":"PASS",
                "task_id":session.task_id,
                "approvals":approvals,
                "event_count":len(runtime.store.list_events(task_id=session.task_id)),
                "health_status":response.status_code,
                "target_pid":target_pid,
            }, indent=2))
            return 0
        finally:
            if blocker.poll() is None:
                blocker.terminate(); blocker.wait(timeout=3)
            if target_pid and psutil.pid_exists(target_pid):
                try:
                    executor = runtime.gateway.resolve("process.start") if "runtime" in locals() else None
                    proc = getattr(executor, "started_processes", {}).get(target_pid) if executor else None
                    if proc is not None:
                        proc.terminate(); await asyncio.wait_for(proc.wait(), timeout=3)
                    else:
                        p = psutil.Process(target_pid); p.terminate(); p.wait(timeout=3)
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
