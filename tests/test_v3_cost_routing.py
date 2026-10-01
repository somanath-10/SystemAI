from pathlib import Path

from systemai.contracts.models import RiskLevel
from systemai.cost import CostBudget, CostController, UsageRecord
from systemai.intelligence import InferenceTier, LocalFirstModelRouter, RoutingRequest
from systemai.orchestration.event_store import EventStore


def test_cost_records_persist_and_route_respects_budget(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "runtime.sqlite3")
    cost = CostController(store=store)
    cost.set_budget("task-1", CostBudget(max_external_cost_usd=0.01, max_external_calls=1))
    cost.record(UsageRecord(task_id="task-1", provider="local", kind="local_llm"))
    cost.record(UsageRecord(task_id="task-1", provider="cloud", model="small", kind="standard_api", estimated_cost_usd=0.01))

    restored = CostController(store=store)
    totals = restored.totals_for("task-1")
    assert totals.local_calls == 1
    assert totals.external_calls == 1
    assert store.verify_chain()

    decision = LocalFirstModelRouter(cost).route(RoutingRequest(
        task_id="task-1", purpose="diagnose", complexity=0.9, risk=RiskLevel.HIGH,
        local_llm_available=False, local_small_available=True,
    ))
    assert decision.tier == InferenceTier.LOCAL_SMALL
    assert "external escalation blocked" in decision.reason
