from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings


def _client(tmp_path: Path, *, calls: int = 1, vision_calls: int = 0) -> TestClient:
    settings = Settings(
        _env_file=None, enable_openai=True, OPENAI_API_KEY="fixture-key",
        openai_model="fixture-model", openai_input_usd_per_million=10,
        openai_output_usd_per_million=20, openai_pricing_verified_at=date.today(),
        openai_max_input_tokens=100, openai_max_output_tokens=20,
        openai_max_task_spend_usd=0.01, openai_max_task_calls=calls,
        openai_max_task_vision_calls=vision_calls,
    )
    return TestClient(create_app(tmp_path / "data", settings=settings), base_url="http://127.0.0.1:8765")


def _task(client: TestClient, tmp_path: Path) -> str:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()["task_id"]


def test_openai_response_is_explicit_metered_and_not_logged(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task_id = _task(client, tmp_path)
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        assert request.headers["authorization"] == "Bearer fixture-key"
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 20})
        return httpx.Response(200, json={
            "status": "completed", "model": "fixture-model", "service_tier": "default",
            "usage": {"input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
            "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "safe answer"}]}],
        })

    client.app.state.runtime.openai.transport = httpx.MockTransport(respond)
    endpoint = f"/tasks/{task_id}/inference/openai"
    assert client.post(endpoint, json={"prompt": "private prompt"}).status_code == 422
    result = client.post(endpoint, json={"prompt": "private prompt", "confirm_external": True})
    assert result.status_code == 200
    assert result.json()["text"] == "safe answer"
    assert seen[0][0] == "/v1/responses/input_tokens"
    assert seen[1][1]["store"] is False and seen[1][1]["tools"] == []
    assert seen[0][1]["input"] == seen[1][1]["input"]
    assert client.get(f"/tasks/{task_id}/cost").json()["totals"]["external_calls"] == 1
    assert client.post(endpoint, json={"prompt": "again", "confirm_external": True}).status_code == 409
    assert len(seen) == 2
    assert "private prompt" not in json.dumps(client.get("/events").json())
    assert "fixture-key" not in json.dumps(client.get("/events").json())
    assert client.app.state.runtime.store.verify_chain()


def test_openai_timeout_keeps_reservation_across_restart(tmp_path: Path) -> None:
    client = _client(tmp_path, calls=2)
    task_id = _task(client, tmp_path)

    def fail(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 20})
        raise httpx.ConnectError("test failure")

    client.app.state.runtime.openai.transport = httpx.MockTransport(fail)
    endpoint = f"/tasks/{task_id}/inference/openai"
    assert client.post(endpoint, json={"prompt": "hello", "confirm_external": True}).status_code == 503
    record = client.get(f"/tasks/{task_id}/cost").json()["records"][0]
    assert record["metadata"]["billing_state"] == "reserved"
    restarted = _client(tmp_path, calls=2)
    restarted.app.state.runtime.openai.transport = httpx.MockTransport(fail)
    assert restarted.post(endpoint, json={"prompt": "again", "confirm_external": True}).status_code == 409
    assert restarted.app.state.runtime.store.verify_chain()


def test_openai_vision_requires_vision_budget(tmp_path: Path) -> None:
    client = _client(tmp_path, vision_calls=0)
    task_id = _task(client, tmp_path)
    endpoint = f"/tasks/{task_id}/inference/openai"
    import base64
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    assert client.post(endpoint, json={"prompt": "describe", "image_base64": image,
                                       "confirm_external": True}).status_code == 409
    assert client.get(f"/tasks/{task_id}/cost").json()["records"] == []


def test_openai_vision_uses_counted_image_input(tmp_path: Path) -> None:
    client = _client(tmp_path, vision_calls=1)
    task_id = _task(client, tmp_path)
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 30})
        return httpx.Response(200, json={
            "status": "completed", "model": "fixture-model", "service_tier": "default",
            "usage": {"input_tokens": 30, "output_tokens": 4, "total_tokens": 34},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "an image"}]}],
        })

    client.app.state.runtime.openai.transport = httpx.MockTransport(respond)
    import base64
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    result = client.post(f"/tasks/{task_id}/inference/openai", json={
        "prompt": "describe", "image_base64": image, "confirm_external": True,
    })
    assert result.status_code == 200
    assert seen[0]["input"] == seen[1]["input"]
    assert seen[1]["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert client.get(f"/tasks/{task_id}/cost").json()["totals"]["external_vision_calls"] == 1


def test_old_zero_budget_task_stays_zero_budget_after_cloud_enabled(tmp_path: Path) -> None:
    disabled = TestClient(create_app(tmp_path / "data", settings=Settings(_env_file=None)),
                          base_url="http://127.0.0.1:8765")
    task_id = _task(disabled, tmp_path)
    enabled = _client(tmp_path)
    assert enabled.get(f"/tasks/{task_id}/cost").json()["budget"]["max_external_calls"] == 0
    assert enabled.post(f"/tasks/{task_id}/inference/openai",
                        json={"prompt": "hello", "confirm_external": True}).status_code == 409


def test_openai_is_disabled_by_default(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data", settings=Settings(_env_file=None)),
                        base_url="http://127.0.0.1:8765")
    task_id = _task(client, tmp_path)
    assert client.get("/inference/status").json()["openai"]["configured"] is False
    assert client.post(f"/tasks/{task_id}/inference/openai",
                       json={"prompt": "hello", "confirm_external": True}).status_code == 503


def test_expired_prices_and_mismatched_model_fail_closed(tmp_path: Path) -> None:
    client = _client(tmp_path, calls=2)
    task_id = _task(client, tmp_path)
    client.app.state.runtime.openai.pricing_verified_at = date.today() - timedelta(days=31)
    assert client.post(f"/tasks/{task_id}/inference/openai",
                       json={"prompt": "hello", "confirm_external": True}).status_code == 503
    assert client.get(f"/tasks/{task_id}/cost").json()["records"] == []
    client.app.state.runtime.openai.pricing_verified_at = date.today()

    def wrong_model(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 20})
        return httpx.Response(200, json={"status": "completed", "model": "different-model",
                                         "service_tier": "default", "usage": {"input_tokens": 20,
                                         "output_tokens": 4, "total_tokens": 24}, "output": []})

    client.app.state.runtime.openai.transport = httpx.MockTransport(wrong_model)
    assert client.post(f"/tasks/{task_id}/inference/openai",
                       json={"prompt": "hello", "confirm_external": True}).status_code == 503
    assert client.get(f"/tasks/{task_id}/cost").json()["records"][0]["metadata"]["billing_state"] == "reserved"
