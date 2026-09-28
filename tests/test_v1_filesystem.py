from pathlib import Path

import pytest

from systemai.contracts.models import ActionIntent, ActionTarget, ResourceScope
from systemai.core.capabilities import default_capabilities
from systemai.execution.filesystem_v1 import FileSystemExecutorV1
from systemai.orchestration import EventStore
from systemai.security.approvals import ApprovalStore
from systemai.security.kernel import SecurityContext, SecurityKernelV1
from systemai.security.signing import CapabilitySigner, CapabilityVerifier


def _executor(tmp_path: Path):
    signer = CapabilitySigner.generate()
    kernel = SecurityKernelV1(registry=default_capabilities(), signer=signer, approvals=ApprovalStore(tmp_path / "events.sqlite3"))
    executor = FileSystemExecutorV1(
        verifier=CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id="filesystem", device_id="local"),
        event_store=EventStore(tmp_path / "events.sqlite3"),
    )
    return kernel, executor


@pytest.mark.asyncio
async def test_file_read_is_bounded_and_moves_do_not_overwrite(tmp_path: Path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("abcdef")
    destination.write_text("preserve")
    kernel, executor = _executor(tmp_path)
    action = ActionIntent(
        task_id="t1",
        capability="file.read",
        target=ActionTarget(path=str(source)),
        parameters={"max_bytes": 3},
        expected_result="read source",
        resource_scope=[ResourceScope(kind="filesystem", value=str(tmp_path), recursive=True)],
    )
    auth = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="filesystem", allowed_roots=(tmp_path,), autonomy_mode="standard_auto"))
    result = await executor.execute(action, capability_token=auth.capability_token)
    assert result.output["text"] == "abc"
    assert result.output["truncated"] is True
    assert result.output["sha256"] is not None

    move = action.model_copy(update={"capability": "file.move", "parameters": {"destination": str(destination)}, "expected_result": "move source"})
    auth = kernel.authorize(move, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="filesystem", allowed_roots=(tmp_path,), autonomy_mode="standard_auto"))
    result = await executor.execute(move, capability_token=auth.capability_token)
    assert result.status.value == "failed"
    assert source.exists()
    assert destination.read_text() == "preserve"
