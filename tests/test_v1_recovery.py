import json
import sys
from pathlib import Path

import psutil
import pytest

from systemai.contracts.models import ActionJournalStatus
from systemai.v1 import build_v1_runtime


@pytest.mark.asyncio
async def test_pending_approval_survives_runtime_restart(tmp_path: Path):
    project = tmp_path / "project"
    (project / ".systemai").mkdir(parents=True)
    (project / ".systemai" / "project.json").write_text(
        json.dumps({"name": "project", "runtime": "python", "start": [sys.executable, "app.py"]})
    )
    data_dir = tmp_path / "runtime"
    first = build_v1_runtime(data_dir=data_dir)
    session = await first.create_developer_task("Start the project", project, autonomy_mode="assist")
    assert session.state.value == "waiting_for_approval"

    restarted = build_v1_runtime(data_dir=data_dir)
    restored = restarted.sessions[session.task_id]
    assert restored.state.value == "waiting_for_approval"
    assert restored.pending_approvals == session.pending_approvals
    assert restored.autonomy_mode == "assist"


@pytest.mark.asyncio
async def test_interrupted_action_cannot_be_resumed_without_reconciliation(tmp_path: Path):
    project = tmp_path / "project"
    (project / ".systemai").mkdir(parents=True)
    (project / ".systemai" / "project.json").write_text(
        json.dumps({"name": "project", "runtime": "python", "start": [sys.executable, "app.py"]})
    )
    runtime = build_v1_runtime(data_dir=tmp_path / "runtime")
    session = await runtime.create_developer_task("Start the project", project)
    action = next(iter(session.graph.nodes.values())).action
    runtime.journal.transition(action, ActionJournalStatus.AUTHORIZED)
    runtime.journal.transition(action, ActionJournalStatus.DISPATCHING)
    runtime.journal.transition(action, ActionJournalStatus.COMMIT_STATUS_UNKNOWN)
    runtime.pause(session.task_id)
    with pytest.raises(ValueError, match="manual reconciliation"):
        await runtime.resume(session.task_id)


@pytest.mark.asyncio
async def test_resource_wait_resumes_after_the_lease_is_released(tmp_path: Path):
    project = tmp_path / "project"
    (project / ".systemai").mkdir(parents=True)
    (project / ".systemai" / "project.json").write_text(
        json.dumps({"name": "project", "runtime": "python", "start": [sys.executable, "-c", "import time; time.sleep(5)"]})
    )
    runtime = build_v1_runtime(data_dir=tmp_path / "runtime")
    session = await runtime.create_developer_task("Start the project", project)
    action_id = next(iter(session.pending_approvals))
    lease = runtime.leases.acquire_many([f"filesystem:{project}"], task_id="other", node_id="other")[0]
    runtime.approve(session.task_id, action_id, approved=True)
    try:
        session = await runtime.run(session.task_id)
        assert session.state.value == "waiting_for_resource"
        runtime.leases.release(lease.lease_id)
        session = await runtime.resume(session.task_id)
        assert session.state.value == "completed"
    finally:
        runtime.leases.release(lease.lease_id)
        result = session.results.get(next(iter(session.graph.nodes.values())).action.action_id)
        if result and result.output.get("pid"):
            try:
                proc = psutil.Process(result.output["pid"])
                proc.terminate()
                proc.wait(timeout=3)
            except psutil.NoSuchProcess:
                pass
