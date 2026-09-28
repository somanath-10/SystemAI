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


def test_v1_api_allows_local_ui_preflight(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"))
    response = client.options(
        "/tasks/developer-diagnosis",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
