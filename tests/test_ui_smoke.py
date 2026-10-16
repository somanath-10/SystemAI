import json
import shutil
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

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
            task = {"task_id": "task_manual", "goal": {"objective": "Fixture task"}, "project_root": "/fixture", "state": "completed", "pending_approvals": {}, "diagnosis": {}, "steps": []}
            notes, rules, requests = [], [], []
            sockets, page_errors, creations = [], [], []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            access_token = 'fixture-access-' + 'a' * 64
            reject_access = False
            await page.route("http://127.0.0.1:8787/authenticate", lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'media_token': 'b' * 64}), headers={"access-control-allow-origin": f"http://127.0.0.1:{server.server_port}", "access-control-allow-credentials": "true", "access-control-allow-headers": "authorization", "access-control-allow-methods": "POST"}))

            def bridge_fixture(socket):
                sockets.append(socket)
                socket.send(json.dumps({"type": "authenticated", "media_token": "c" * 64}))
                socket.send(json.dumps({"type": "ready", "session_id": "task_assistant", "servers": ["SystemAI"]}))

            await page.route_web_socket("ws://127.0.0.1:8787/", bridge_fixture)

            async def api_fixture(route):
                path = urlsplit(route.request.url).path
                if route.request.method != 'OPTIONS':
                    assert route.request.headers.get('authorization') == 'Bearer ' + access_token
                    if reject_access:
                        await route.fulfill(status=401, content_type='application/json', headers={"access-control-allow-origin": "*"}, body='{"detail":"Unauthorized"}')
                        return
                body = route.request.post_data_json if route.request.post_data else {}
                requests.append((path, route.request.method, body))
                payload = {"items": []}
                if path == '/auth/check': payload = {'authenticated': True, 'operation_timeout_ms': 250_000}
                elif path == "/desktop/status": payload = {"available": False, "allowed_applications": []}
                elif path == "/browser/status": payload = {"available": True, "configured": True, "allowed_origins": ["http://127.0.0.1:5802"]}
                elif path == "/inference/status": payload = {"models": {"local_embedding": True}}
                elif path == "/tasks/browser" or path == "/tasks/task_manual": payload = task
                elif path in {"/tasks/task_assistant", "/tasks/task_assistant_next"}: payload = {**task, "task_id": path.rsplit("/", 1)[-1], "goal": {"objective": "Voice assistant conversation"}}
                elif path == "/tasks/task_late": payload = {**task, "task_id": "task_late", "goal": {"objective": "Interrupted older task"}}
                elif path == "/tasks": payload = {"items": [{"task_id": task["task_id"], "objective": task["goal"]["objective"], "state": task["state"]}]}
                elif path.endswith("/cost"): payload = {"cost_task_id": "task_assistant", "totals": {"external_calls": 0, "external_cost_usd": 0, "local_calls": 0}, "budget": {"max_external_calls": 0, "max_external_cost_usd": 0}}
                elif path == "/events":
                    context = parse_qs(urlsplit(route.request.url).query).get("task_id", ["global"])[0]
                    payload = {"items": [{"event_id": "event_" + context, "event_type": "AssistantSessionCreated" if context == "task_assistant" else "TaskCompleted", "created_at": "2026-10-12T10:00:00Z"}]}
                elif path == "/monitor/status": payload = {"running": True}
                elif path == "/monitor/rules":
                    if route.request.method == "POST": rules.append({**body, "rule_id": "rule_fixture", "enabled": True})
                    payload = {"items": rules}
                elif path.endswith("/state"): rules[0]["enabled"] = body["enabled"]
                elif path.endswith("/memory"):
                    notes.append({"note_id": "note_fixture", "content": body["content"], "score": 1})
                    payload = notes[0]
                elif path.endswith("/memory/search"): payload = {"items": notes}
                elif path.endswith("/memory/note_fixture"): notes.clear()
                elif "/skill-candidate" in path: payload = {"status": "reviewable", "candidate_hash": "fixture_hash"}
                elif path.endswith("/inference/route"): payload = {"tier": "local_llm", "reason": "Local model is available"}
                if path == "/tasks/browser": creations.append(route.request.url)
                await route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"}, body=json.dumps(payload))

            await page.route("http://127.0.0.1:8765/**", api_fixture)
            await page.goto(f"http://127.0.0.1:{server.server_port}/?view=tasks")
            assert await page.get_by_role('heading', name='Unlock workspace').is_visible()
            await page.get_by_label('Local access key').fill(access_token)
            await page.get_by_role('button', name='Unlock', exact=True).click()
            await page.get_by_role('button', name='New task', exact=True).wait_for()
            assert await page.locator(".satellite").count() == 14
            assert not await page.get_by_label("Project directory").is_visible()

            await page.get_by_role("button", name="New task", exact=True).click()
            assert await page.get_by_role("dialog").is_visible()
            assert await page.get_by_label("Project directory").is_visible()
            await page.get_by_role("button", name="Browser", exact=True).click(timeout=3000)
            assert await page.get_by_label("Page URL").is_visible()
            await page.get_by_role("button", name="AI", exact=True).click()
            assert await page.get_by_label("Model").is_visible()
            await page.get_by_role("group", name="AI provider").get_by_role("button", name="OpenAI").click()
            assert not await page.get_by_label("Model").is_visible()
            assert await page.get_by_label("Prompt").is_visible()
            await page.keyboard.press("Escape")
            assert not await page.get_by_role("dialog").is_visible()
            assert not await page.get_by_label("Page URL").is_visible()
            await page.goto(f"http://127.0.0.1:{server.server_port}/")
            await page.wait_for_function("sessionStorage.getItem('systemai.assistantSession') === 'task_assistant'")
            await page.wait_for_function("sessionStorage.getItem('systemai.mediaKey') === 'c'.repeat(64)")
            sockets[0].send(json.dumps({"type": "authenticated", "media_token": "invalid"}))
            sockets[0].send(json.dumps({"type": "authenticated", "media_token": "d" * 64}))
            await page.wait_for_function("sessionStorage.getItem('systemai.mediaKey') === 'd'.repeat(64)")
            await page.locator('canvas:not(.hands-canvas)').wait_for(state='visible')
            assert await page.locator('canvas:not(.hands-canvas)').count() == 1
            assert await page.get_by_role('button', name='INITIALISE').is_visible()
            await page.get_by_role('button', name='Message', exact=True).click()
            assert await page.get_by_role('dialog', name='Message').is_visible()
            await page.get_by_label('AI engine').select_option('local')
            await page.keyboard.press('Escape')
            await page.get_by_role('button', name='Message', exact=True).click()
            assert await page.get_by_label('AI engine').input_value() == 'local'
            await page.keyboard.press('Escape')
            await page.get_by_role('button', name='Task Center', exact=True).click()
            frame = page.frame_locator('iframe[title="Task Center"]')
            await frame.get_by_role('button', name='New task', exact=True).wait_for(state='visible')
            assert await frame.get_by_role('button', name='New task', exact=True).is_visible()
            await frame.get_by_role('button', name='New task', exact=True).click()
            await frame.get_by_role('button', name='Browser', exact=True).click()
            await frame.get_by_role('button', name='Open page').click()
            await frame.get_by_role('region', name='Current run').wait_for(state='visible')
            await page.get_by_role('button', name='Close Task Center').click()
            for malformed in ['null', '[]', '{"type":"ready","servers":[null,4,{}]}']:
                sockets[0].send(malformed)
            sockets[0].send(json.dumps({"type": "task", "task_id": "task_late", "interrupted": True}))
            sockets[0].send(json.dumps({"type": "ready", "session_id": "task_assistant_next", "servers": ["SystemAI"]}))
            await page.wait_for_function("sessionStorage.getItem('systemai.assistantSession') === 'task_assistant_next'")
            assert await page.evaluate("sessionStorage.getItem('systemai.selectedTask')") == "task_manual"
            assert not page_errors
            assert "parent_task_id=task_assistant" in creations[0]
            await page.get_by_role('button', name='Task Center', exact=True).click()
            await frame.get_by_text('Fixture task', exact=True).wait_for(state='visible')
            await frame.get_by_role('button', name='Workspace tools', exact=True).click()
            await frame.get_by_role('button', name='Memory', exact=True).click()
            await frame.get_by_label('Note', exact=True).fill('Remember fixture')
            await frame.get_by_role('button', name='Save note', exact=True).click()
            await frame.get_by_label('Search notes', exact=True).fill('fixture')
            await frame.get_by_role('button', name='Search notes', exact=True).click()
            await frame.get_by_text('Remember fixture', exact=True).wait_for(state='visible')
            await frame.get_by_role('button', name='Delete note', exact=True).click()
            await frame.get_by_text('Remember fixture', exact=True).wait_for(state='detached')
            await frame.get_by_role('button', name='Alerts', exact=True).click()
            await frame.get_by_label('Exact process name').fill('fixture')
            await frame.get_by_role('button', name='Create alert', exact=True).click()
            await frame.get_by_role('button', name='Disable', exact=True).click()
            await frame.get_by_role('button', name='Enable', exact=True).wait_for(state='visible')
            await frame.get_by_role('button', name='Review', exact=True).click()
            await frame.get_by_role('button', name='Load candidate', exact=True).click()
            await frame.get_by_role('button', name='Retain review', exact=True).click()
            await frame.get_by_role('button', name='Routing', exact=True).click()
            await frame.get_by_role('button', name='Check routing', exact=True).click()
            await frame.get_by_text('local_llm · Local model is available', exact=True).wait_for(state='visible')
            await frame.get_by_role('button', name='Audit', exact=True).click()
            assert await frame.get_by_text('TaskCompleted', exact=True).is_visible()
            assert any(path.endswith('/skill-candidate/review') and body['candidate_hash'] == 'fixture_hash' for path, method, body in requests)
            await frame.get_by_role('button', name='Close workspace tools').click()
            await page.get_by_role('button', name='Close Task Center').click()
            reject_access = True
            await page.get_by_role('button', name='Task Center', exact=True).click()
            await page.get_by_role('heading', name='Unlock workspace').wait_for(state='visible')
            assert await page.evaluate("sessionStorage.getItem('systemai.accessKey')") == ''
            assert await page.evaluate("sessionStorage.getItem('systemai.mediaKey')") == ''
            reject_access = False
            await page.get_by_label('Local access key').fill(access_token)
            await page.get_by_role('button', name='Unlock', exact=True).click()
            await page.get_by_role('button', name='INITIALISE').wait_for(state='visible')
            await page.wait_for_function("sessionStorage.getItem('systemai.mediaKey') === 'c'.repeat(64)")
            await sockets[-1].close(code=1008, reason='authentication required')
            await page.get_by_role('heading', name='Unlock workspace').wait_for(state='visible')
            assert await page.evaluate("sessionStorage.getItem('systemai.accessKey')") == ''
            assert not page_errors
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
