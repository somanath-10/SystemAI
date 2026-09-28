from pathlib import Path

from systemai.contracts.models import ActionIntent, ActionTarget, RiskLevel
from systemai.core.capabilities import default_capabilities
from systemai.security.policy import PolicyContext, PolicyKernel


def test_unknown_capability_denied():
    kernel = PolicyKernel(default_capabilities())
    action = ActionIntent(task_id="t", capability="unknown.action", expected_result="x")
    decision = kernel.evaluate(action, PolicyContext(task_id="t"))
    assert decision.decision == "deny"


def test_high_risk_requires_approval(tmp_path: Path):
    kernel = PolicyKernel(default_capabilities())
    p = tmp_path / "x.txt"
    action = ActionIntent(
        task_id="t",
        capability="file.delete",
        target=ActionTarget(path=str(p)),
        expected_result="deleted",
        risk=RiskLevel.HIGH,
    )
    decision = kernel.evaluate(action, PolicyContext(task_id="t", allowed_roots=[tmp_path]))
    assert decision.decision == "require_approval"


def test_filesystem_scope_is_enforced(tmp_path: Path):
    kernel = PolicyKernel(default_capabilities())
    action = ActionIntent(
        task_id="t",
        capability="file.read",
        target=ActionTarget(path="/etc/passwd"),
        expected_result="read",
        risk=RiskLevel.OBSERVE,
    )
    decision = kernel.evaluate(action, PolicyContext(task_id="t", allowed_roots=[tmp_path]))
    assert decision.decision == "deny"
