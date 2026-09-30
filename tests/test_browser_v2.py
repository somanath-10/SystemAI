import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from systemai.config import Settings
from systemai.contracts.models import ActionIntent
from systemai.runtime import build_runtime


class BrowserFixture(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/download":
            body = b"systemai browser download\n"
            self.send_response(200)
            self.send_header("Content-Disposition", 'attachment; filename="report.txt"')
            self.send_header("Content-Type", "text/plain")
        else:
            body = b'''<!doctype html><title>Safe Test</title>
<button onclick="document.querySelector('#result').textContent='Done'">Change</button>
<input id="name" aria-label="Name"><input id="upload" type="file">
<a href="/download">Download</a><div id="result">Pending</div>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


@pytest.mark.asyncio
async def test_signed_browser_workflow_with_isolated_profile(tmp_path: Path) -> None:
    if not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("installed Chrome is required for native browser integration")
    server = ThreadingHTTPServer(("127.0.0.1", 0), BrowserFixture)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    settings = Settings(
        _env_file=None,
        enable_browser=True,
        enable_desktop=False,
        browser_headless=True,
        browser_channel="chrome",
        browser_allowed_origins=origin,
        browser_profile_dir=tmp_path / "profile",
        browser_download_dir=tmp_path / "downloads",
    )
    runtime = build_runtime(data_dir=tmp_path / "data", settings=settings)
    try:
        denied = await runtime.gateway.resolve("browser.navigate").execute(
            ActionIntent(task_id="bare", capability="browser.navigate", expected_result="open page")
        )
        assert denied.status.value == "rejected"
        assert not (tmp_path / "profile").exists()

        page = await runtime.create_browser_task(capability="browser.navigate", url=origin + "/", expected_title="Safe Test")
        assert page.state.value == "completed", page.snapshot()
        assert (tmp_path / "profile").is_dir()
        with pytest.raises(ValueError, match="allowlist"):
            await runtime.create_browser_task(capability="browser.navigate", url="https://example.com/")

        click = await runtime.create_browser_task(
            capability="browser.click", url=origin + "/", role="button", name="Change", expected_text="Done"
        )
        assert click.state.value == "waiting_for_approval"
        action_id = next(iter(click.pending_approvals))
        runtime.approve(click.task_id, action_id, approved=True)
        await runtime.run(click.task_id)
        assert click.state.value == "completed", click.snapshot()

        fill = await runtime.create_browser_task(capability="browser.fill", url=origin + "/", selector="#name", value="hello")
        assert "hello" not in json.dumps(fill.snapshot())
        action_id = next(iter(fill.pending_approvals))
        runtime.approve(fill.task_id, action_id, approved=True)
        await runtime.run(fill.task_id)
        assert fill.state.value == "completed", fill.snapshot()
        assert "hello" not in json.dumps(runtime.store.list_events(task_id=fill.task_id))

        download = await runtime.create_browser_task(capability="browser.download", url=origin + "/", role="link", name="Download")
        assert download.state.value == "waiting_for_approval", download.snapshot()["steps"][0]["last_error"]
        action_id = next(iter(download.pending_approvals))
        runtime.approve(download.task_id, action_id, approved=True)
        await runtime.run(download.task_id)
        assert download.state.value == "completed", download.snapshot()
        path = Path(download.snapshot()["steps"][0]["result"]["output"]["path"])
        assert path.parent == tmp_path / "downloads"
        assert path.read_bytes() == b"systemai browser download\n"

        file_path = tmp_path / "upload.txt"
        file_path.write_text("upload fixture")
        upload = await runtime.create_browser_task(capability="browser.upload", url=origin + "/", selector="#upload", path=str(file_path))
        action_id = next(iter(upload.pending_approvals))
        runtime.approve(upload.task_id, action_id, approved=True)
        await runtime.run(upload.task_id)
        assert upload.state.value == "completed", upload.snapshot()
        assert runtime.store.verify_chain()
    finally:
        if runtime.browser:
            await runtime.browser.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
