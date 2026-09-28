from pathlib import Path

from fastapi.testclient import TestClient

from systemai.api.v1_server import create_app


def test_v1_health_and_capabilities(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == "1.0.0"
    assert health.json()["event_chain_valid"] is True

    capabilities = client.get("/capabilities")
    assert capabilities.status_code == 200
    assert len(capabilities.json()["items"]) >= 30
