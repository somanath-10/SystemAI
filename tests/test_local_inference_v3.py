from __future__ import annotations

import json
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.cost import CostController
from systemai.intelligence.confidence import evidence_confidence
from systemai.intelligence.ollama import LocalModelUnavailable, OllamaClient
from systemai.contracts.models import ActionIntent, VerificationResult, VerificationSpec, VerificationStatus


class OllamaFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/tags":
            self.send_error(404)
            return
        self._json({"models": [{"name": "test-text:latest"}, {"name": "test-vision:latest"},
                                {"name": "test-embed:latest", "digest": self.server.digest}]})

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/embed"}:
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.last_request = body
        if self.path == "/api/embed":
            vector = [0.0, 1.0] if body["input"] == "blue" else [1.0, 0.0]
            self._json({"model": body["model"], "embeddings": [vector], "prompt_eval_count": 2})
            return
        self._json({"message": {"content": "local response"}, "prompt_eval_count": 7, "eval_count": 3})

    def _json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def ollama_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaFixture)
    server.digest = "sha256:original"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.asyncio
async def test_local_chat_records_real_usage_and_fails_closed(ollama_server) -> None:
    provider = OllamaClient(f"http://127.0.0.1:{ollama_server.server_port}", text="test-text:latest", vision="test-vision:latest")
    cost = CostController()
    assert (await provider.status())["models"]["local_llm"] is True
    assert "test-text:latest" in (await provider.status())["installed_models"]
    result = await provider.generate(task_id="task-1", prompt="hello", kind="local_llm", cost=cost)
    assert result.text == "local response"
    assert cost.records_for("task-1")[0].input_tokens == 7
    assert cost.totals_for("task-1").external_calls == 0
    assert ollama_server.last_request["stream"] is False
    vision = await provider.generate(task_id="task-1", prompt="describe", kind="local_vlm", cost=cost, image=b"\x89PNG\r\n\x1a\nexample")
    assert vision.text == "local response"
    assert len(ollama_server.last_request["messages"][0]["images"]) == 1
    assert cost.records_for("task-1")[1].image_count == 1
    selected = await provider.generate(task_id="task-1", prompt="selected", kind="local_llm", cost=cost,
                                       model_override="test-vision:latest")
    assert selected.model == "test-vision:latest"
    with pytest.raises(LocalModelUnavailable, match="not installed"):
        await provider.generate(task_id="task-1", prompt="selected", kind="local_llm", cost=cost,
                                model_override="uninstalled-model")
    with pytest.raises(ValueError):
        OllamaClient("https://example.com", text="test-text:latest")


def test_local_inference_api_uses_installed_model_and_persists_usage(tmp_path: Path, ollama_server) -> None:
    settings = Settings(_env_file=None, ollama_url=f"http://127.0.0.1:{ollama_server.server_port}", ollama_text_model="test-text:latest")
    client = TestClient(create_app(tmp_path / "data", settings=settings), base_url="http://127.0.0.1:8765")
    project = tmp_path / "project"
    project.mkdir()
    task_id = client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()["task_id"]
    assert client.get("/inference/status").json()["models"]["local_llm"] is True
    routed = client.post(f"/tasks/{task_id}/inference/route", json={"task_id": task_id, "purpose": "reason"})
    assert routed.json()["tier"] == "local_llm"
    response = client.post(f"/tasks/{task_id}/inference/generate", json={"prompt": "hello"})
    assert response.status_code == 200
    assert response.json()["text"] == "local response"
    assert client.get(f"/tasks/{task_id}/cost").json()["totals"]["local_calls"] == 1
    assert client.app.state.runtime.store.verify_chain()
    assert client.post(f"/tasks/{task_id}/inference/generate", json={"prompt": "hi", "image_base64": "broken"}).status_code == 400
    fake_image = base64.b64encode(b"RIFFxxxxNOPE").decode()
    assert client.post(f"/tasks/{task_id}/inference/generate", json={"prompt": "hi", "image_base64": fake_image}).status_code == 400


def test_confidence_uses_independent_evidence() -> None:
    action = ActionIntent(task_id="task-1", node_id="n", capability="file.read", expected_result="file exists", verification=[VerificationSpec(kind="file.exists")])
    assert evidence_confidence(action, None)["score"] == 0
    passed = VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED, checks=[{"kind": "file.exists", "passed": True}])
    assert evidence_confidence(action, passed)["score"] == 0.95
    missing = VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED)
    assert evidence_confidence(action, missing)["score"] == 0.2


def test_semantic_memory_is_task_scoped_durable_and_model_specific(tmp_path: Path, ollama_server) -> None:
    settings = Settings(_env_file=None, ollama_url=f"http://127.0.0.1:{ollama_server.server_port}",
                        ollama_embedding_model="test-embed:latest")
    data_dir = tmp_path / "data"
    client = TestClient(create_app(data_dir, settings=settings), base_url="http://127.0.0.1:8765")
    project = tmp_path / "project"
    project.mkdir()
    task_id = client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()["task_id"]
    other_task = client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()["task_id"]

    red = client.post(f"/tasks/{task_id}/memory", json={"content": "red"})
    assert red.status_code == 200
    assert ollama_server.last_request["truncate"] is False
    blue = client.post(f"/tasks/{task_id}/memory", json={"content": "blue"})
    assert blue.status_code == 200
    assert client.post(f"/tasks/{other_task}/memory/search", json={"query": "red"}).json()["items"] == []

    restored = TestClient(create_app(data_dir, settings=settings), base_url="http://127.0.0.1:8765")
    search = restored.post(f"/tasks/{task_id}/memory/search", json={"query": "red", "limit": 1})
    assert search.status_code == 200
    assert search.json()["items"] == [{"note_id": red.json()["note_id"], "content": "red", "score": 1.0}]
    assert restored.get(f"/tasks/{task_id}/cost").json()["totals"]["local_calls"] == 3
    assert "\"content\":\"red\"" not in json.dumps(restored.get("/events").json())

    ollama_server.digest = "sha256:replaced"
    assert restored.post(f"/tasks/{task_id}/memory/search", json={"query": "red"}).json()["items"] == []
    assert restored.delete(f"/tasks/{task_id}/memory/{red.json()['note_id']}").json() == {"deleted": True}
    assert restored.delete(f"/tasks/{task_id}/memory/{red.json()['note_id']}").status_code == 404
    assert restored.app.state.runtime.store.verify_chain()
