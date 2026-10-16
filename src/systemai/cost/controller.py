from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from systemai.orchestration.event_store import EventStore


ProviderKind = Literal[
    "deterministic",
    "local_small",
    "local_llm",
    "local_vlm",
    "local_embedding",
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
    call_id: str = Field(default_factory=lambda: f"model_{uuid4().hex[:16]}")
    task_id: str
    provider: str
    model: str | None = None
    kind: ProviderKind
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    audio_seconds: float = Field(default=0.0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0)
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

    def __init__(self, store: "EventStore | None" = None) -> None:
        self.store = store
        self._budgets: dict[str, CostBudget] = {}
        self._records: list[UsageRecord] = []
        self._lock = Lock()
        self._active_external: set[str] = set()
        self._external_leases: dict[str, tuple[str, float]] = {}

    def _expire_leases(self) -> None:
        for call_id, (_, deadline) in list(self._external_leases.items()):
            if deadline <= monotonic():
                self._external_leases.pop(call_id)
                self._active_external.discard(call_id)

    def lease_external(self, call_id: str, worker_id: str) -> None:
        with self._lock:
            if call_id not in self._active_external:
                raise ValueError("external call is not active")
            self._external_leases[call_id] = (worker_id, monotonic() + 90)

    def renew_external(self, call_id: str, worker_id: str) -> None:
        with self._lock:
            self._expire_leases()
            if call_id not in self._external_leases or self._external_leases[call_id][0] != worker_id:
                raise ValueError("external worker lease is missing or expired")
            self._external_leases[call_id] = (worker_id, monotonic() + 90)

    def set_budget(self, task_id: str, budget: CostBudget) -> None:
        with self._lock:
            self._budgets[task_id] = budget

    def budget_for(self, task_id: str) -> CostBudget:
        with self._lock:
            return self._budgets.get(task_id, CostBudget())

    def records_for(self, task_id: str) -> list[UsageRecord]:
        if self.store is not None:
            return [UsageRecord.model_validate({**record, "model": record["model"] or None,
                                                "image_count": record["images"]})
                    for record in self.store.model_calls_for(task_id)]
        with self._lock:
            return [record.model_copy(deep=True) for record in self._records if record.task_id == task_id]

    def totals_for(self, task_id: str) -> UsageTotals:
        records = self.records_for(task_id)
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
        with self._lock:
            self._expire_leases()
            active = tuple(self._active_external)
        if self.store is not None and self.store.has_unsettled_external(task_id, active_calls=active):
            return False, "previous external charge is unresolved"
        if totals.external_calls + 1 > budget.max_external_calls:
            return False, "external call budget exhausted"
        if totals.external_cost_usd + max(0.0, estimated_cost_usd) > budget.max_external_cost_usd:
            return False, "external dollar budget exhausted"
        if vision and totals.external_vision_calls + 1 > budget.max_external_vision_calls:
            return False, "external vision-call budget exhausted"
        if totals.external_audio_seconds + max(0.0, audio_seconds) > budget.max_external_audio_seconds:
            return False, "external audio budget exhausted"
        return True, "within budget"

    def reserve_external(self, record: UsageRecord) -> None:
        if record.kind not in self.EXTERNAL_KINDS or record.estimated_cost_usd <= 0:
            raise ValueError("external reservation requires a positive estimated charge")
        if self.store is None:
            raise RuntimeError("external inference requires a durable usage store")
        budget = self.budget_for(record.task_id)
        pending = record.model_copy(deep=True)
        pending.metadata["billing_state"] = "reserved"
        with self._lock:
            self._expire_leases()
            reason = self.store.reserve_external_model_call(
                pending.model_dump(mode="json"), max_cost=budget.max_external_cost_usd,
                max_calls=budget.max_external_calls, max_vision_calls=budget.max_external_vision_calls,
                max_audio_seconds=budget.max_external_audio_seconds, active_calls=tuple(self._active_external),
            )
            if reason:
                raise BudgetExceeded(reason)
            self._active_external.add(record.call_id)
        self.store.append("ModelUsageReserved", {"provider": record.provider, "model": record.model,
                                                 "estimated_cost_usd": record.estimated_cost_usd}, task_id=record.task_id)

    def settle_external(self, record: UsageRecord) -> None:
        if self.store is None:
            raise RuntimeError("external inference requires a durable usage store")
        overrun = self.store.settle_external_model_call(
            record.call_id, input_tokens=record.input_tokens, output_tokens=record.output_tokens,
            estimated_cost_usd=record.estimated_cost_usd, latency_ms=record.latency_ms,
        )
        self.abandon_external(record.call_id)
        self.store.append("ModelUsageRecorded", {"provider": record.provider, "model": record.model,
                                                 "kind": record.kind, "estimated_cost_usd": record.estimated_cost_usd,
                                                 "overrun": overrun}, task_id=record.task_id)
        if overrun:
            raise BudgetExceeded("external response exceeded its reserved estimate; task cloud budget is blocked")

    def abandon_external(self, call_id: str) -> None:
        """Keep an uncertain reservation held; only release its active-request marker."""
        with self._lock:
            self._active_external.discard(call_id)
            self._external_leases.pop(call_id, None)

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
        if self.store is not None:
            self.store.record_model_call(record.model_dump(mode="json"))
            self.store.append(
                "ModelUsageRecorded",
                {"provider": record.provider, "model": record.model, "kind": record.kind, "estimated_cost_usd": record.estimated_cost_usd},
                task_id=record.task_id,
            )
            return
        with self._lock:
            self._records.append(record)
