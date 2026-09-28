from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

from pydantic import BaseModel, Field


ProviderKind = Literal[
    "deterministic",
    "local_small",
    "local_llm",
    "local_vlm",
    "specialist_api",
    "standard_api",
    "premium_api",
]


class CostBudget(BaseModel):
    """Per-task external inference budget.

    Local inference still consumes power/compute, but it does not consume a cloud
    token budget. External providers are always checked against this object before
    a call is allowed to start.
    """

    max_external_cost_usd: float = Field(default=0.25, ge=0)
    max_external_calls: int = Field(default=4, ge=0)
    max_external_vision_calls: int = Field(default=1, ge=0)
    max_external_audio_seconds: float = Field(default=120.0, ge=0)
    prefer_local: bool = True


class UsageRecord(BaseModel):
    task_id: str
    provider: str
    model: str | None = None
    kind: ProviderKind
    input_tokens: int = 0
    output_tokens: int = 0
    image_count: int = 0
    audio_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


@dataclass(slots=True)
class UsageTotals:
    external_calls: int = 0
    external_vision_calls: int = 0
    external_audio_seconds: float = 0.0
    external_cost_usd: float = 0.0
    local_calls: int = 0


class BudgetExceeded(RuntimeError):
    pass


class CostController:
    """Thread-safe usage ledger and pre-flight budget gate.

    The router can ask `can_use_external` before escalating. Provider adapters
    should record actual or estimated usage after each call. The runtime can expose
    these totals in the UI and audit log.
    """

    EXTERNAL_KINDS = {"specialist_api", "standard_api", "premium_api"}

    def __init__(self) -> None:
        self._budgets: dict[str, CostBudget] = {}
        self._records: list[UsageRecord] = []
        self._lock = Lock()

    def set_budget(self, task_id: str, budget: CostBudget) -> None:
        with self._lock:
            self._budgets[task_id] = budget

    def budget_for(self, task_id: str) -> CostBudget:
        with self._lock:
            return self._budgets.get(task_id, CostBudget())

    def records_for(self, task_id: str) -> list[UsageRecord]:
        with self._lock:
            return [record.model_copy(deep=True) for record in self._records if record.task_id == task_id]

    def totals_for(self, task_id: str) -> UsageTotals:
        with self._lock:
            records = [r for r in self._records if r.task_id == task_id]
        totals = UsageTotals()
        for record in records:
            if record.kind in self.EXTERNAL_KINDS:
                totals.external_calls += 1
                totals.external_cost_usd += record.estimated_cost_usd
                totals.external_audio_seconds += record.audio_seconds
                if record.image_count:
                    totals.external_vision_calls += 1
            else:
                totals.local_calls += 1
        return totals

    def can_use_external(
        self,
        task_id: str,
        *,
        estimated_cost_usd: float = 0.0,
        vision: bool = False,
        audio_seconds: float = 0.0,
    ) -> tuple[bool, str]:
        budget = self.budget_for(task_id)
        totals = self.totals_for(task_id)
        if totals.external_calls + 1 > budget.max_external_calls:
            return False, "external call budget exhausted"
        if totals.external_cost_usd + max(0.0, estimated_cost_usd) > budget.max_external_cost_usd:
            return False, "external dollar budget exhausted"
        if vision and totals.external_vision_calls + 1 > budget.max_external_vision_calls:
            return False, "external vision-call budget exhausted"
        if totals.external_audio_seconds + max(0.0, audio_seconds) > budget.max_external_audio_seconds:
            return False, "external audio budget exhausted"
        return True, "within budget"

    def require_external_budget(self, task_id: str, **kwargs) -> None:
        allowed, reason = self.can_use_external(task_id, **kwargs)
        if not allowed:
            raise BudgetExceeded(reason)

    def record(self, record: UsageRecord) -> None:
        if record.kind in self.EXTERNAL_KINDS:
            self.require_external_budget(
                record.task_id,
                estimated_cost_usd=record.estimated_cost_usd,
                vision=record.image_count > 0,
                audio_seconds=record.audio_seconds,
            )
        with self._lock:
            self._records.append(record)
