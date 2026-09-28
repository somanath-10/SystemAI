import sys
from pathlib import Path

import pytest

from systemai.contracts.models import ActionIntent, ActionTarget, ResourceScope
from systemai.execution.sandbox_v1 import SandboxExecutorV1
from systemai.orchestration import EventStore
from systemai.security.approvals import ApprovalStore
from systemai.security.kernel import SecurityContext, SecurityKernelV1
from systemai.security.signing import CapabilitySigner, CapabilityVerifier
from systemai.core.capabilities import default_capabilities


@pytest.mark.asyncio
async def test_sandbox_fails_closed_without_an_isolation_backend(tmp_path: Path, monkeypatch):
    store = EventStore(tmp_path / "e.sqlite3")
    signer = CapabilitySigner.generate()
    kernel = SecurityKernelV1(registry=default_capabilities(), signer=signer, approvals=ApprovalStore(tmp_path / "e.sqlite3"))
    verifier = CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id="sandbox", device_id="local")
    executor = SandboxExecutorV1(verifier=verifier, event_store=store, allowed_binaries={Path(sys.executable).name})
    monkeypatch.setattr(executor, "_backend_for", lambda _profile: "none")
    action = ActionIntent(
        task_id="t1",
        capability="sandbox.run",
        target=ActionTarget(path=str(tmp_path)),
        parameters={"argv": [sys.executable, "-c", "print('ok')"], "cwd": str(tmp_path), "profile": "read_only"},
        expected_result="print ok",
        resource_scope=[ResourceScope(kind="filesystem", value=str(tmp_path), recursive=True)],
    )
    auth = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="sandbox", allowed_roots=(tmp_path,), autonomy_mode="standard_auto"))
    # Project-originated shell/coding work is intentionally approval gated in V1.
    if auth.decision.decision == "require_approval":
        kernel.approvals.decide(auth.approval_id, approved=True, approved_by="u")
        auth = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="sandbox", allowed_roots=(tmp_path,), autonomy_mode="standard_auto", approval_id=auth.approval_id))
    result = await executor.execute(action, capability_token=auth.capability_token)
    assert result.status.value == "failed"
    assert "cannot be enforced" in result.error
