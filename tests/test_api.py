from pathlib import Path
from stat import S_IMODE

import pytest
from conftest import TestClient

from systemai.api.local_server import create_app


def test_health_and_capabilities(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    assert S_IMODE((tmp_path / "data").stat().st_mode) == 0o700
    assert S_IMODE((tmp_path / "data" / "keys").stat().st_mode) == 0o700
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == "1.0.0"
    assert health.json()["event_chain_valid"] is True

    capabilities = client.get("/capabilities")
    assert capabilities.status_code == 200
    assert len(capabilities.json()["items"]) >= 30


@pytest.mark.parametrize("origin", ["http://localhost:5802", "http://127.0.0.1:5802"])
def test_api_allows_local_ui_preflight(tmp_path: Path, origin: str) -> None:
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    response = client.options(
        "/tasks/developer-diagnosis",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_local_api_rejects_untrusted_browser_writes_and_host(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    assert client.post("/tasks/desktop-observation", headers={"Origin": "https://malicious.example"}).status_code == 403
    assert client.get("/health", headers={"Host": "malicious.example"}).status_code == 400


def test_browser_api_rejects_unlisted_origin_without_task(tmp_path: Path) -> None:
    from systemai.config import Settings

    settings = Settings(_env_file=None, enable_browser=True, browser_allowed_origins="http://127.0.0.1:5802")
    client = TestClient(create_app(tmp_path / "data", settings=settings), base_url="http://127.0.0.1:8765")
    assert client.get("/browser/status").json()["configured"] is True
    response = client.post("/tasks/browser", json={"capability": "browser.navigate", "url": "https://example.com/"})
    assert response.status_code == 400
    assert client.app.state.runtime.sessions == {}


def test_cost_and_routing_api_for_an_existing_task(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"), base_url="http://127.0.0.1:8765")
    project = tmp_path / "project"
    project.mkdir()
    created = client.post("/tasks/developer-diagnosis", json={"project_root": str(project)}).json()
    task_id = created["task_id"]

    cost = client.get(f"/tasks/{task_id}/cost")
    assert cost.status_code == 200
    assert cost.json()["totals"]["external_calls"] == 0

    routed = client.post(f"/tasks/{task_id}/inference/route", json={
        "task_id": task_id,
        "purpose": "classify a local diagnosis",
        "complexity": 0.1,
    })
    assert routed.status_code == 409
    assert "no permitted inference tier" in routed.json()["detail"]
