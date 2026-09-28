import json
from pathlib import Path


def test_v1_eval_catalog_has_50_fixed_cases():
    p = Path(__file__).parents[1] / "evals" / "systemai" / "catalog.json"
    data = json.loads(p.read_text())
    assert data["count"] == 50
    assert len(data["tasks"]) == 50
    categories = {x["category"] for x in data["tasks"]}
    assert {"files","git","process","ports","environment","verification","recovery","security","browser","desktop"} <= categories
