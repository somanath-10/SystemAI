import json
import shutil
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


@pytest.mark.asyncio
async def test_orb_and_task_modal() -> None:
    if not shutil.which("npm") or not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("npm and Chrome are required for UI smoke test")
    playwright = pytest.importorskip("playwright.async_api")
    ui = Path(__file__).resolve().parents[1] / "apps" / "desktop" / "ui"
    subprocess.run(["npm", "run", "build"], cwd=ui, check=True, capture_output=True, text=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ui / "dist"), **kwargs)

        def log_message(self, format: str, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with playwright.async_playwright() as browser_tools:
            browser = await browser_tools.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 820})

            async def api_fixture(route):
                payload = {"available": False, "allowed_applications": []} if "desktop" in route.request.url else {"available": True, "configured": True, "allowed_origins": ["http://127.0.0.1:5802"]}
                await route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"}, body=json.dumps(payload))

            await page.route("http://127.0.0.1:8765/**", api_fixture)
            await page.goto(f"http://127.0.0.1:{server.server_port}/")
            assert await page.locator(".satellite").count() == 14
            assert not await page.get_by_label("Project directory").is_visible()

            await page.get_by_role("button", name="New task", exact=True).click()
            assert await page.get_by_role("dialog").is_visible()
            assert await page.get_by_label("Project directory").is_visible()
            await page.get_by_role("button", name="Browser", exact=True).click(timeout=3000)
            assert await page.get_by_label("Page URL").is_visible()
            await page.keyboard.press("Escape")
            assert not await page.get_by_role("dialog").is_visible()
            assert not await page.get_by_label("Page URL").is_visible()
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
