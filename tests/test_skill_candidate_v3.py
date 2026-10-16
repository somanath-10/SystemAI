from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from conftest import TestClient

from systemai.api.local_server import create_app
from systemai.contracts.models import (
    ActionIntent, Sensitivity, SourceProvenance, TrustLevel,
    VerificationResult, VerificationSpec, VerificationStatus,
)
from systemai.core.capabilities import default_capabilities
from systemai.skills.registry import preview_candidate


def test_candidate_preview_requires_trusted_independent_evidence_without_exposing_parameters() -> None:
    action = ActionIntent(
        task_id="task-1", node_id="read", capability="file.read", expected_result="file remains present",
        parameters={"private_value": "do-not-expose"},
        verification=[VerificationSpec(kind="file.exists")],
        provenance=[SourceProvenance(trust_class=TrustLevel.TRUSTED, source_type="user")],
    )
    verified = VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED,
                                  checks=[{"kind": "file.exists", "passed": True}])
    snapshot = {"task_id": "task-1", "state": "completed", "steps": [{
        "state": "succeeded", "action": action.model_dump(mode="json"),
        "verification": verified.model_dump(mode="json"),
    }]}
    preview = preview_candidate(snapshot, default_capabilities())
    assert preview["status"] == "reviewable"
    assert preview["qualified"] is False and preview["replay_authorized"] is False
    assert "do-not-expose" not in json.dumps(preview)
    assert preview["steps"][0]["canonical_risk"] == "observe"

    snapshot["steps"][0]["action"]["provenance"] = [
        SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="webpage",
                         sensitivity=Sensitivity.SECRET).model_dump(mode="json")
    ]
    blocked = preview_candidate(snapshot, default_capabilities())
    assert blocked["status"] == "blocked"
    assert {"untrusted_provenance", "secret_provenance"}.issubset(blocked["reasons"])

    snapshot["steps"][0]["action"]["capability"] = "file.delete"
    snapshot["steps"][0]["verification"] = None
    blocked = preview_candidate(snapshot, default_capabilities())
    assert {"risk_above_low", "independent_evidence_missing"}.issubset(blocked["reasons"])


def test_skill_candidate_api_is_read_only_and_fail_closed(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    client = TestClient(create_app(data_dir), base_url="http://127.0.0.1:8765")
    project = tmp_path / "project"
    project.mkdir()
    task_id = client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()["task_id"]
    result = client.get(f"/tasks/{task_id}/skill-candidate")
    assert result.status_code == 200
    assert result.json()["status"] == "blocked"
    assert result.json()["replay_authorized"] is False
    candidate_hash = result.json()["candidate_hash"]
    endpoint = f"/tasks/{task_id}/skill-candidate/review"
    assert client.post(endpoint, json={"candidate_hash": candidate_hash, "decision": "retain"}).status_code == 409
    assert client.post(endpoint, json={"candidate_hash": "0" * 64, "decision": "reject"}).status_code == 409
    assert client.post(endpoint, json={"candidate_hash": candidate_hash, "decision": "approve"}).status_code == 422
    reviewed = client.post(endpoint, json={"candidate_hash": candidate_hash, "decision": "reject"})
    assert reviewed.status_code == 200
    assert reviewed.json()["review"]["non_authorizing"] is True
    assert reviewed.json()["qualified"] is False
    assert reviewed.json()["replay_authorized"] is False
    client.app.state.runtime.close()
    restored = TestClient(create_app(data_dir), base_url="http://127.0.0.1:8765")
    assert restored.get(f"/tasks/{task_id}/skill-candidate").json()["review"]["decision"] == "reject"
    assert restored.get("/tasks/unknown/skill-candidate").status_code == 404
    assert restored.post("/tasks/unknown/skill-candidate/review", json={"candidate_hash": candidate_hash, "decision": "reject"}).status_code == 404
    assert client.app.state.runtime.store.verify_chain()


def test_reviewable_candidate_retention_is_bound_to_current_snapshot(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    action = ActionIntent(
        task_id="task-review", node_id="read", capability="file.read", expected_result="file remains present",
        verification=[VerificationSpec(kind="file.exists")],
        provenance=[SourceProvenance(trust_class=TrustLevel.TRUSTED, source_type="user")],
    )
    verified = VerificationResult(action_id=action.action_id, status=VerificationStatus.PASSED,
                                  checks=[{"kind": "file.exists", "passed": True}])
    snapshot = {"task_id": action.task_id, "state": "completed", "steps": [{
        "state": "succeeded", "action": action.model_dump(mode="json"),
        "verification": verified.model_dump(mode="json"),
    }]}
    client.app.state.runtime.sessions[action.task_id] = SimpleNamespace(snapshot=lambda: snapshot)
    endpoint = f"/tasks/{action.task_id}/skill-candidate"
    current = client.get(endpoint).json()
    assert current["status"] == "reviewable"
    reviewed = client.post(f"{endpoint}/review", json={"candidate_hash": current["candidate_hash"], "decision": "retain"})
    assert reviewed.status_code == 200
    assert reviewed.json()["review"]["decision"] == "retain"
    assert reviewed.json()["qualified"] is False and reviewed.json()["replay_authorized"] is False
    snapshot["state"] = "paused"
    changed = client.get(endpoint).json()
    assert changed["candidate_hash"] != current["candidate_hash"]
    assert changed["review"] is None
    assert client.post(f"{endpoint}/review", json={"candidate_hash": current["candidate_hash"], "decision": "reject"}).status_code == 409
    assert client.app.state.runtime.store.verify_chain()
