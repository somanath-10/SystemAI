import asyncio
import os
import subprocess
import sys
from pathlib import Path
from stat import S_IMODE

import pytest
from fastapi.testclient import TestClient as RawClient

from conftest import TestClient
from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.runtime import build_runtime
from systemai.security.local_access import local_api_token
from test_workflow_regressions import seed_read


@pytest.mark.parametrize('invalid', ['short', 'a' * 32 + ' ', 'a' * 32 + '\t', 'a' * 32 + '\x00', 'a' * 32 + '\x7f', 'a' * 32 + 'é'])
def test_configured_access_key_rejects_non_header_characters(tmp_path, invalid):
    with pytest.raises(ValueError, match='printable'):
        local_api_token(tmp_path, invalid)
    assert local_api_token(tmp_path, '!' * 32 + '~') == '!' * 32 + '~'


def test_local_access_key_is_required_even_with_forged_origin(tmp_path):
    app = create_app(tmp_path / 'data')
    runtime = app.state.runtime
    session, action = seed_read(runtime, tmp_path)
    action.requires_confirmation = True
    asyncio.run(runtime.run(session.task_id))
    assert session.state.value == 'waiting_for_approval'
    raw = RawClient(app, base_url='http://127.0.0.1:8765')
    for headers in ({}, {'Origin': 'http://127.0.0.1:5802'}, {'Authorization': 'Bearer wrong'}):
        assert raw.get('/tasks', headers=headers).status_code == 401
        assert raw.post('/assistant/sessions', headers=headers).status_code == 401
        assert raw.post(f'/tasks/{session.task_id}/approval', headers=headers,
                        json={'action_id': action.action_id, 'approved': True}).status_code == 401
    assert not session.results
    assert S_IMODE((tmp_path / 'data/keys/local-api-token').stat().st_mode) == 0o600
    authenticated = raw.get('/auth/check', headers={'Authorization': 'Bearer ' + app.state.api_token}).json()
    assert authenticated == {'authenticated': True, 'operation_timeout_ms': 250_000}
    assert raw.get('/health').status_code == 200
    authorized = TestClient(app, base_url='http://127.0.0.1:8765')
    assert authorized.post(f'/tasks/{session.task_id}/approval', json={'action_id': action.action_id, 'approved': True}).json()['state'] == 'completed'


@pytest.mark.asyncio
async def test_second_runtime_cannot_recover_an_active_action(tmp_path):
    settings = Settings(_env_file=None)
    runtime = build_runtime(data_dir=tmp_path / 'data', settings=settings)
    session, action = seed_read(runtime, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    execute = runtime.gateway.execute
    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return await execute(*args, **kwargs)
    runtime.gateway.execute = slow
    running = asyncio.create_task(runtime.run(session.task_id))
    await entered.wait()
    try:
        with pytest.raises(RuntimeError, match='Another SystemAI runtime'):
            build_runtime(data_dir=tmp_path / 'data', settings=settings)
        with pytest.raises(RuntimeError, match='while a task is executing'):
            runtime.close()
        assert runtime.journal.get(action.action_id)['status'] == 'dispatching'
        code = 'from pathlib import Path; from systemai.runtime import build_runtime; build_runtime(data_dir=Path(__import__("sys").argv[1]))'
        child = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'data')], env={**os.environ, 'PYTHONPATH': 'src'}, capture_output=True, text=True, timeout=10)
        assert child.returncode != 0 and 'Another SystemAI runtime' in child.stderr
        assert runtime.journal.get(action.action_id)['status'] == 'dispatching'
    finally:
        release.set()
    assert (await running).state.value == 'completed'
    runtime.close()
    restored = build_runtime(data_dir=tmp_path / 'data', settings=settings)
    assert restored.sessions[session.task_id].state.value == 'completed'
    with pytest.raises(RuntimeError, match='closed'):
        await runtime.run(session.task_id)


def test_module_import_does_not_initialize_a_runtime(tmp_path):
    directory = tmp_path / 'unused'
    code = 'import systemai.api.local_server'
    subprocess.run([sys.executable, '-c', code], env={**os.environ, 'PYTHONPATH': 'src', 'SYSTEMAI_DATA_DIR': str(directory)}, check=True, timeout=10)
    assert not directory.exists()


def test_bridge_leases_allow_overlap_but_expire_fail_closed(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('systemai.cost.controller.monotonic', lambda: clock[0])
    settings = Settings(_env_file=None, openai_max_task_spend_usd=5, openai_max_task_calls=100, openai_max_task_audio_seconds=1800)
    client = TestClient(create_app(tmp_path / 'data', settings=settings), base_url='http://127.0.0.1:8765')
    task = client.post('/assistant/sessions').json()['task_id']
    endpoint = f'/tasks/{task}/assistant/external-usage'
    reserve = {'phase': 'reserve', 'worker_id': '00000000-0000-4000-8000-000000000001', 'provider': 'deepgram', 'feature': 'stt', 'estimated_cost_usd': 0.01, 'audio_seconds': 30}
    first = client.post(endpoint, json=reserve).json()
    second = client.post(endpoint, json={**reserve, 'provider': 'cartesia', 'feature': 'tts'})
    assert second.status_code == 200
    assert client.post(endpoint, json={**reserve, 'phase': 'renew', **first}).status_code == 200
    wrong_worker = {**reserve, 'phase': 'settle', **first, 'worker_id': '00000000-0000-4000-8000-000000000002'}
    assert client.post(endpoint, json=wrong_worker).status_code == 404
    clock[0] += 91
    assert client.post(endpoint, json={**reserve, 'phase': 'renew', **first}).status_code == 409
    assert client.post(endpoint, json=reserve).status_code == 409
    assert client.post(endpoint, json={**reserve, 'phase': 'settle', **first}).status_code == 200
    assert client.post(endpoint, json={**reserve, 'phase': 'settle', **first}).status_code == 409
    assert client.post(endpoint, json={**reserve, 'provider': 'cartesia', 'feature': 'tts', 'phase': 'settle', **second.json()}).status_code == 200
    assert client.post(endpoint, json=reserve).status_code == 200


def test_abandoned_and_restarted_bridge_calls_block_new_charges(tmp_path):
    settings = Settings(_env_file=None, openai_max_task_spend_usd=5, openai_max_task_calls=100)
    client = TestClient(create_app(tmp_path / 'data', settings=settings), base_url='http://127.0.0.1:8765')
    task = client.post('/assistant/sessions').json()['task_id']
    endpoint = f'/tasks/{task}/assistant/external-usage'
    reserve = {'phase': 'reserve', 'worker_id': '00000000-0000-4000-8000-000000000001', 'provider': 'cartesia', 'feature': 'tts', 'estimated_cost_usd': 0.01}
    first = client.post(endpoint, json=reserve).json()
    assert client.post(endpoint, json={**reserve, 'phase': 'abandon', **first}).status_code == 200
    assert client.post(endpoint, json=reserve).status_code == 409
    assert client.post(endpoint, json={**reserve, 'phase': 'settle', **first}).status_code == 200
    second = client.post(endpoint, json=reserve).json()
    client.app.state.runtime.close()
    restored = TestClient(create_app(tmp_path / 'data', settings=settings), base_url='http://127.0.0.1:8765')
    assert restored.post(endpoint, json=reserve).status_code == 409
    assert restored.post(endpoint, json={**reserve, 'phase': 'settle', **second}).status_code == 200
