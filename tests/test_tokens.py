import pytest

from systemai.security.tokens import CapabilityTokenError, CapabilityTokenService


def test_capability_token_is_bound_to_action():
    svc = CapabilityTokenService(b"k" * 32)
    token = svc.issue(task_id="t1", action_id="a1", capability="file.delete")
    payload = svc.verify(token, task_id="t1", action_id="a1", capability="file.delete")
    assert payload["task_id"] == "t1"
    with pytest.raises(CapabilityTokenError):
        svc.verify(token, task_id="t1", action_id="a2", capability="file.delete")
