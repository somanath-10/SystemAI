import json
from pathlib import Path

import pytest
from conftest import TestClient

from systemai.api.local_server import create_app
from systemai.config import Settings
from systemai.contracts.models import ActionIntent, ActionResult, ActionTarget, ActionJournalStatus, GoalContract, StepState, TaskState, VerificationSpec
from systemai.core.task_graph import TaskGraph, TaskNode
from systemai.orchestration.runtime import TaskSession
from systemai.runtime import build_runtime


def seed_read(runtime, root: Path, task_id="read-test"):
    source = root / "fixture.txt"
    source.write_text("fixture")
    action = ActionIntent(task_id=task_id, node_id="read", capability="file.read", target=ActionTarget(path=str(source)),
                          expected_result="Read fixture", verification=[VerificationSpec(kind="file.exists", parameters={"path": str(source)})])
    session = TaskSession(task_id=task_id, contract=GoalContract(objective="Read fixture"), project_root=root,
                          graph=TaskGraph.from_nodes(task_id, [TaskNode(node_id="read", title="Read", action=action)]), diagnosis={})
    runtime.sessions[task_id] = session
    runtime._persist(session)
    return session, action


def test_connector_budget_does_not_require_openai_configuration(tmp_path):
    runtime = build_runtime(data_dir=tmp_path, settings=Settings(_env_file=None, enable_openai=False,
                            openai_max_task_spend_usd=0.5, openai_max_task_calls=3))
    session = runtime.create_assistant_session()
    assert runtime.cost.budget_for(session.task_id).max_external_cost_usd == 0.5
    assert runtime.cost.budget_for(session.task_id).max_external_calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("step_state", [StepState.PENDING, StepState.RUNNING])
async def test_pre_dispatch_authorization_restart_gets_fresh_authorization(tmp_path, step_state):
    settings = Settings(_env_file=None)
    data = tmp_path / "data"
    runtime = build_runtime(data_dir=data, settings=settings)
    session, action = seed_read(runtime, tmp_path)
    session.graph.nodes["read"].state = step_state
    runtime._persist(session)
    runtime.journal.prepare(action)
    runtime.journal.transition(action, ActionJournalStatus.AUTHORIZED, token_nonce="expired-token")
    runtime.close()
    restored = build_runtime(data_dir=data, settings=settings)
    finished = await restored.resume(session.task_id)
    assert finished.state == TaskState.COMPLETED
    assert restored.journal.get(action.action_id)["token_nonce"] != "expired-token"
    assert restored.store.verify_chain()


@pytest.mark.parametrize("state", [TaskState.CANCELLED, TaskState.COMPLETED, TaskState.FAILED, TaskState.USER_TAKEOVER])
def test_terminal_tasks_cannot_be_revived_by_api_controls(tmp_path, state):
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    session, _ = seed_read(client.app.state.runtime, tmp_path)
    session.state = state
    for control in ("pause", "take-control", "resume"):
        assert client.post(f"/tasks/{session.task_id}/{control}").status_code == 409
    assert session.state == state
    assert not session.results


def test_events_cli_is_read_only_even_with_inflight_journal(tmp_path, monkeypatch, capsys):
    from systemai.main import main
    runtime = build_runtime(data_dir=tmp_path / "data", settings=Settings(_env_file=None))
    _, action = seed_read(runtime, tmp_path)
    runtime.journal.prepare(action)
    runtime.journal.transition(action, ActionJournalStatus.AUTHORIZED)
    runtime.journal.transition(action, ActionJournalStatus.DISPATCHING)
    before = runtime.store.list_events()
    monkeypatch.setattr("sys.argv", ["systemai", "--data-dir", str(tmp_path / "data"), "events"])
    main()
    assert json.loads(capsys.readouterr().out) == before
    assert runtime.journal.get(action.action_id)["status"] == "dispatching"
    assert runtime.store.list_events() == before
    assert runtime.store.list_events(limit=1, latest=True)[0]["event_id"] == before[-1]["event_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ActionJournalStatus.EFFECT_OBSERVED, ActionJournalStatus.VERIFIED])
async def test_restart_after_observation_never_reexecutes(tmp_path, status):
    settings = Settings(_env_file=None)
    runtime = build_runtime(data_dir=tmp_path / "data", settings=settings)
    session, action = seed_read(runtime, tmp_path)
    session.state = TaskState.VERIFYING
    session.graph.nodes["read"].state = StepState.RUNNING
    runtime._persist(session)
    runtime.journal.prepare(action)
    result = ActionResult(action_id=action.action_id, status="completed", effect="confirmed", executor="fixture")
    for state in (ActionJournalStatus.AUTHORIZED, ActionJournalStatus.DISPATCHING, ActionJournalStatus.DISPATCHED, ActionJournalStatus.EFFECT_OBSERVED):
        runtime.journal.transition(action, state, result=result)
    if status == ActionJournalStatus.VERIFIED:
        runtime.journal.transition(action, status)
    runtime.close()
    restored = build_runtime(data_dir=tmp_path / "data", settings=settings)
    async def forbidden(*args, **kwargs):
        pytest.fail("A durably observed action must not execute again")
    restored.gateway.execute = forbidden
    finished = await restored.resume(session.task_id)
    assert finished.state == TaskState.COMPLETED
    assert restored.journal.get(action.action_id)["status"] == "verified"
    assert restored.store.verify_chain()
