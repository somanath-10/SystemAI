from pathlib import Path

import pytest

from systemai.contracts.models import ActionIntent, ActionResult, ActionTarget, ResourceScope, RiskLevel, SourceProvenance, TrustLevel, VerificationSpec
from systemai.core.capabilities import default_capabilities
from systemai.security.approvals import ApprovalStore
from systemai.security.kernel import SecurityContext, SecurityKernelV1
from systemai.security.signing import CapabilitySigner, CapabilityVerifier
from systemai.verification.v1_verifier import VerifierV1


def build(tmp_path: Path):
    signer = CapabilitySigner.generate()
    approvals = ApprovalStore(tmp_path / "s.sqlite3")
    kernel = SecurityKernelV1(registry=default_capabilities(), signer=signer, approvals=approvals)
    return signer, approvals, kernel


def test_planner_cannot_lower_canonical_risk(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    action = ActionIntent(
        task_id="t1",
        capability="process.terminate",
        target=ActionTarget(process_id=123),
        parameters={"pid": 123},
        expected_result="stop process",
        risk_hint=RiskLevel.LOW,
        resource_scope=[ResourceScope(kind="process", value="123")],
    )
    result = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="process", autonomy_mode="standard_auto"))
    assert result.decision.risk == RiskLevel.HIGH
    assert result.decision.decision == "require_approval"


def test_untrusted_process_start_requires_approval(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    action = ActionIntent(
        task_id="t1",
        capability="process.start",
        target=ActionTarget(path=str(root)),
        parameters={"argv": ["python", "app.py"], "cwd": str(root)},
        expected_result="start",
        resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True)],
        provenance=[SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="repository")],
    )
    result = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="process", allowed_roots=(root,), autonomy_mode="standard_auto"))
    assert result.decision.decision == "require_approval"
    assert result.approval_id


def test_capability_is_bound_to_action_and_single_use(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    action = ActionIntent(task_id="t1", capability="process.list", expected_result="list")
    auth = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="process", autonomy_mode="standard_auto"))
    assert auth.capability_token
    verifier = CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id="process", device_id="local")
    claims = verifier.verify(auth.capability_token, action=action)
    assert claims.action_id == action.action_id
    with pytest.raises(ValueError, match="replay"):
        verifier.verify(auth.capability_token, action=action)


@pytest.mark.parametrize(
    ("capability", "parameters"),
    [
        ("file.move", {"destination": "/tmp/outside-project"}),
        ("process.start", {"argv": ["python", "app.py"], "cwd": "/tmp/outside-project"}),
    ],
)
def test_parameter_paths_cannot_escape_project_scope(tmp_path: Path, capability: str, parameters: dict):
    signer, approvals, kernel = build(tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    action = ActionIntent(
        task_id="t1",
        capability=capability,
        target=ActionTarget(path=str(root)),
        parameters=parameters,
        expected_result="bounded action",
        resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True)],
    )
    result = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="filesystem", allowed_roots=(root,), autonomy_mode="standard_auto"))
    assert result.decision.decision == "deny"


def test_remote_health_check_is_not_a_v1_action(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    action = ActionIntent(task_id="t1", capability="http.health", target=ActionTarget(url="https://example.com/health"), expected_result="healthy")
    result = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="http", autonomy_mode="standard_auto"))
    assert result.decision.decision == "deny"


def test_remote_database_probe_is_not_a_v1_action(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    action = ActionIntent(task_id="t1", capability="database.inspect", parameters={"host": "db.example.com", "port": 5432}, expected_result="healthy")
    result = kernel.authorize(action, SecurityContext(actor_id="u", session_id="s", task_id="t1", executor_id="diagnostic", autonomy_mode="standard_auto"))
    assert result.decision.decision == "deny"


def test_approval_summary_shows_command_without_secret_values(tmp_path: Path):
    signer, approvals, kernel = build(tmp_path)
    action = ActionIntent(
        task_id="t1",
        capability="process.start",
        parameters={"argv": ["python", "app.py"], "API_KEY": "do-not-show"},
        expected_result="start",
    )
    summary = kernel.canonical_summary(action, RiskLevel.MEDIUM, True)
    assert '"argv": ["python", "app.py"]' in summary
    assert "do-not-show" not in summary


def test_approval_cannot_be_changed_after_decision(tmp_path: Path):
    _signer, approvals, _kernel = build(tmp_path)
    approval_id = approvals.request(action_id="a1", task_id="t1", requested_by="u", canonical_summary="summary", reason="required")
    approvals.decide(approval_id, approved=True, approved_by="u")
    with pytest.raises(ValueError, match="already decided"):
        approvals.decide(approval_id, approved=False, approved_by="u")


@pytest.mark.asyncio
async def test_verifier_cannot_probe_files_outside_the_action_scope(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    action = ActionIntent(
        task_id="t1",
        capability="file.read",
        target=ActionTarget(path=str(root / "inside.txt")),
        verification=[VerificationSpec(kind="file.exists", parameters={"path": str(outside)})],
        expected_result="read project file",
        resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True)],
    )
    result = ActionResult(action_id=action.action_id, status="completed", effect="confirmed", executor="filesystem")
    verification = await VerifierV1().verify(action, result)
    assert verification.status.value == "failed"
    assert verification.checks[0]["error"] == "file verification is outside action scope"
