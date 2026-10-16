import base64
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from conftest import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.cost import BudgetExceeded, UsageRecord


def assistant(tmp_path: Path):
    settings = Settings(_env_file=None, enable_openai=True, OPENAI_API_KEY="test-secret", openai_model="test-model",
                        openai_input_usd_per_million=10, openai_output_usd_per_million=20,
                        openai_pricing_verified_at=date.today(), openai_max_input_tokens=200,
                        openai_max_output_tokens=100, openai_max_task_spend_usd=1, openai_max_task_calls=20,
                        openai_max_task_vision_calls=5, enable_openai_speech=True,
                        openai_stt_max_call_cost_usd=0.01, openai_tts_max_call_cost_usd=0.01,
                        openai_max_task_audio_seconds=600, openai_web_search_usd_per_call=0.01,
                        openai_image_model="test-image-model", openai_image_max_call_cost_usd=0.02)
    client = TestClient(create_app(tmp_path / "data", settings=settings), base_url="http://127.0.0.1:8765")
    session = client.post("/assistant/sessions").json()["task_id"]
    return client, session


def test_speech_budget_is_shared_and_enforced_without_openai(tmp_path: Path):
    settings = Settings(_env_file=None, enable_openai=False, openai_max_task_spend_usd=5,
                        openai_max_task_calls=100, openai_max_task_audio_seconds=1800)
    client = TestClient(create_app(tmp_path / "data", settings=settings), base_url="http://127.0.0.1:8765")
    session = client.post('/assistant/sessions').json()['task_id']
    budget = client.get(f'/tasks/{session}/cost').json()['budget']
    assert budget['max_external_cost_usd'] == 5
    reserve = {'phase': 'reserve', 'worker_id': '00000000-0000-4000-8000-000000000001', 'provider': 'deepgram', 'feature': 'stt', 'estimated_cost_usd': 4.99, 'audio_seconds': 30}
    record = client.post(f'/tasks/{session}/assistant/external-usage', json=reserve).json()
    assert client.post(f'/tasks/{session}/assistant/external-usage', json={**reserve, 'phase': 'settle', **record}).status_code == 200
    over_budget = {**reserve, 'provider': 'cartesia', 'feature': 'tts', 'estimated_cost_usd': 0.02}
    assert client.post(f'/tasks/{session}/assistant/external-usage', json=over_budget).status_code == 409
    assert client.get(f'/tasks/{session}/cost').json()['totals']['external_cost_usd'] == 4.99
    assert client.post(f'/tasks/{session}/assistant/external-usage', json={**over_budget, 'provider': 'unknown'}).status_code == 422


def sse(output, input_tokens=20, output_tokens=5):
    final = {"type": "response.completed", "response": {"model": "test-model", "service_tier": "default",
             "status": "completed", "output": output,
             "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                       "total_tokens": input_tokens + output_tokens}}}
    return 'data: {"type":"response.output_text.delta","delta":"Ready."}\n\n' + f"data: {json.dumps(final)}\n\n"


def test_streamed_tool_proposal_is_metered_and_never_executes_itself(tmp_path: Path):
    client, session = assistant(tmp_path)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 20})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse([
            {"type": "function_call", "name": "file_delete", "call_id": "call-1", "arguments": '{"path":"private"}'}]))
    runtime = client.app.state.runtime
    runtime.openai.transport = httpx.MockTransport(handler)
    response = client.post(f"/tasks/{session}/assistant/response", json={"input": [{"role": "user", "content": "private prompt"}],
        "tools": [{"name": "file_delete", "parameters": {"type": "object", "properties": {}}}], "confirm_external": True})
    assert response.status_code == 200 and "function_call" in response.text
    assert calls[0]["tools"] == calls[1]["tools"]
    assert calls[1]["store"] is False and calls[1]["stream"] is True
    assert runtime.cost.records_for(session)[0].metadata["billing_state"] == "settled"
    assert runtime.sessions[session].graph.nodes == {}
    events = runtime.store.list_events(task_id=session)
    assert "private prompt" not in json.dumps(events) and "test-secret" not in json.dumps(events)
    assert runtime.store.verify_chain()
    assert client.post(f"/tasks/{session}/assistant/response", json={"input": [{"type": "shell_call"}], "confirm_external": True}).status_code == 422


def test_stt_tts_and_generated_image_use_server_key_and_durable_usage(tmp_path: Path):
    client, session = assistant(tmp_path)
    requests = []
    image = b"\x89PNG\r\n\x1a\nfixture"
    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-secret"
        if request.url.path == "/v1/audio/transcriptions":
            assert b'speech.webm' in request.content
            return httpx.Response(200, json={"text": "hello"})
        if request.url.path == "/v1/audio/speech":
            return httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=b"ID3fixture")
        if request.url.path == "/v1/images/generations":
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image).decode()}]})
        raise AssertionError(request.url)
    runtime = client.app.state.runtime
    runtime.openai.transport = httpx.MockTransport(handler)
    stt = client.post(f"/tasks/{session}/assistant/stt", content=b"recording", headers={"content-type": "audio/webm;codecs=opus"})
    assert stt.json() == {"text": "hello"}
    tts = client.post(f"/tasks/{session}/assistant/tts", json={"text": "hello", "confirm_external": True})
    assert tts.content == b"ID3fixture" and tts.headers["content-type"].startswith("audio/")
    generated = client.post(f"/tasks/{session}/assistant/tools/image", json={"prompt": "a reactor", "confirm_external": True})
    assert generated.status_code == 200
    assert Path(generated.json()["path"]).read_bytes() == image
    assert len(runtime.cost.records_for(session)) == 3
    assert all(record.metadata["billing_state"] == "settled" for record in runtime.cost.records_for(session))
    assert client.post(f"/tasks/{session}/assistant/stt", content=b"x", headers={"content-type": "text/html"}).status_code == 400
    assert client.post(f"/tasks/{session}/assistant/stt", content=b"x", headers={"content-type": "audio/ogg"}).status_code == 400
    assert len(runtime.cost.records_for(session)) == 3
    assert runtime.store.verify_chain()


def test_web_search_preserves_sources_and_accounts_tool_fee(tmp_path: Path):
    client, session = assistant(tmp_path)
    def handler(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 20})
        body = json.loads(request.content)
        assert body["tools"] == [{"type": "web_search"}] and body["max_tool_calls"] == 1
        return httpx.Response(200, content=sse([{"type": "message", "content": [{"type": "output_text",
            "text": "The answer.", "annotations": [{"type": "url_citation", "url": "https://example.com/source", "title": "Source"}]}]}]))
    runtime = client.app.state.runtime
    runtime.openai.transport = httpx.MockTransport(handler)
    found = client.post(f"/tasks/{session}/assistant/tools/search", json={"prompt": "news", "confirm_external": True})
    assert found.json() == {"text": "The answer.", "sources": [{"url": "https://example.com/source", "title": "Source"}]}
    assert runtime.cost.records_for(session)[0].estimated_cost_usd > 0.01


def test_active_audio_and_text_reservations_share_budget_but_abandoned_charge_blocks(tmp_path: Path):
    client, session = assistant(tmp_path)
    cost = client.app.state.runtime.cost
    text = UsageRecord(task_id=session, provider="openai", kind="standard_api", estimated_cost_usd=0.01)
    audio = UsageRecord(task_id=session, provider="openai", kind="specialist_api", estimated_cost_usd=0.01, audio_seconds=30)
    cost.reserve_external(text)
    cost.reserve_external(audio)
    assert cost.totals_for(session).external_calls == 2
    cost.abandon_external(text.call_id)
    with pytest.raises(BudgetExceeded, match="unresolved"):
        cost.reserve_external(UsageRecord(task_id=session, provider="openai", kind="standard_api", estimated_cost_usd=0.01))
    cost.settle_external(audio)


@pytest.mark.parametrize("provider", ["mcp-fixture", "deepgram", "cartesia", "sarvam"])
def test_child_tasks_share_conversation_costs_and_survive_restart(tmp_path: Path, provider: str):
    client, session = assistant(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    child = client.post('/tasks/developer-diagnosis', params={'parent_task_id': session}, json={'project_root': str(project)}).json()
    child_id = child['task_id']
    assert child['parent_task_id'] == session
    assert client.get(f'/tasks/{child_id}/cost').json()['cost_task_id'] == session
    reserve = {'phase': 'reserve', 'worker_id': '00000000-0000-4000-8000-000000000001', 'provider': provider, 'feature': 'read_status', 'estimated_cost_usd': 0.02}
    record = client.post(f'/tasks/{child_id}/assistant/external-usage', json=reserve).json()
    assert client.get(f'/tasks/{session}/cost').json()['totals']['external_calls'] == 1
    concurrent = client.post(f'/tasks/{session}/assistant/external-usage', json=reserve)
    assert concurrent.status_code == 200
    assert client.post(f'/tasks/{session}/assistant/external-usage', json={**reserve, 'phase': 'settle', **concurrent.json()}).status_code == 200
    settle = {**reserve, 'phase': 'settle', **record}
    assert client.post(f'/tasks/{child_id}/assistant/external-usage', json=settle).status_code == 200
    assert client.post(f'/tasks/{child_id}/assistant/external-usage', json=settle).status_code == 409
    assert client.get(f'/tasks/{child_id}/cost').json()['totals']['external_cost_usd'] == 0.04
    assert any(item['task_id'] == child_id for item in client.get('/tasks').json()['items'])
    from systemai.runtime import build_runtime
    client.app.state.runtime.close()
    restored = build_runtime(data_dir=tmp_path / 'data', settings=Settings(_env_file=None))
    assert restored.sessions[child_id].parent_task_id == session
    assert restored.cost_task_id(child_id) == session
    assert restored.store.verify_chain()


def test_assistant_audit_rejects_unbounded_or_sensitive_payloads(tmp_path: Path):
    client, session = assistant(tmp_path)
    assert client.post(f'/tasks/{session}/assistant/events', json={'event': 'AssistantToolStarted', 'turn_id': 'turn', 'tool': 'mcp__fixture__read_status'}).status_code == 200
    assert client.post(f'/tasks/{session}/assistant/events', json={'event': 'UntrustedAction', 'turn_id': 'turn'}).status_code == 422
    assert client.post(f'/tasks/{session}/assistant/events', json={'event': 'AssistantToolStarted', 'turn_id': 'turn', 'tool': 'secret key=abc'}).status_code == 422
    assert client.app.state.runtime.store.verify_chain()
