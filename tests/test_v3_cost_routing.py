from pathlib import Path

from systemai.contracts.models import RiskLevel
from systemai.cost import BudgetExceeded, CostBudget, CostController, UsageRecord
from systemai.intelligence import InferenceTier, LocalFirstModelRouter, Modality, RoutingRequest
import pytest
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


@pytest.mark.parametrize("modality", [Modality.VISION, Modality.AUDIO])
def test_text_model_never_receives_unsupported_modality(modality: Modality) -> None:
    router = LocalFirstModelRouter(CostController())
    with pytest.raises(RuntimeError, match="no permitted inference tier"):
        router.route(RoutingRequest(task_id="t", purpose="analyze", modality=modality,
                                    local_small_available=True, local_llm_available=True))


def test_single_cloud_model_is_not_claimed_as_premium_or_audio() -> None:
    cost = CostController()
    router = LocalFirstModelRouter(cost)
    decision = router.route(RoutingRequest(task_id="t", purpose="reason", complexity=0.95,
                                           external_available=True))
    assert decision.tier == InferenceTier.STANDARD_API
    with pytest.raises(RuntimeError, match="no permitted inference tier"):
        router.route(RoutingRequest(task_id="t", purpose="transcribe", modality=Modality.AUDIO,
                                    external_available=True))


def test_external_reservation_is_durable_and_shared(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "runtime.sqlite3")
    first = CostController(store=store)
    second = CostController(store=store)
    budget = CostBudget(max_external_cost_usd=0.01, max_external_calls=2)
    first.set_budget("task", budget)
    second.set_budget("task", budget)
    record = UsageRecord(task_id="task", provider="openai", model="fixed", kind="standard_api",
                         estimated_cost_usd=0.004)
    first.reserve_external(record)
    with pytest.raises(BudgetExceeded, match="unresolved"):
        second.reserve_external(UsageRecord(task_id="task", provider="openai", model="fixed",
                                            kind="standard_api", estimated_cost_usd=0.004))
    first.settle_external(record.model_copy(update={"input_tokens": 10, "output_tokens": 5,
                                                 "estimated_cost_usd": 0.002}))
    second.reserve_external(UsageRecord(task_id="task", provider="openai", model="fixed",
                                        kind="standard_api", estimated_cost_usd=0.004))
    assert store.verify_chain()
