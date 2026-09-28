from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable, Any


@dataclass(slots=True)
class EvalResult:
    case_id: str
    success: bool
    verified: bool
    unsafe_actions: int = 0
    unauthorized_actions: int = 0
    collateral_damage: int = 0
    human_interventions: int = 0
    recovery_success: bool | None = None
    model_calls: int = 0
    premium_calls: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class EvaluationHarness:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog = json.loads(Path(catalog_path).read_text())

    @property
    def tasks(self) -> list[dict]:
        return list(self.catalog["tasks"])

    def run_callable(self, case_id: str, fn: Callable[[], tuple[bool, bool, dict]]) -> EvalResult:
        started = perf_counter()
        success, verified, details = fn()
        return EvalResult(case_id=case_id, success=success, verified=verified, latency_ms=(perf_counter()-started)*1000, details=details)

    @staticmethod
    def aggregate(results: list[EvalResult]) -> dict[str, Any]:
        total = max(1, len(results))
        return {
            "cases": len(results),
            "task_success_rate": sum(r.success for r in results) / total,
            "verified_task_success_rate": sum(r.verified for r in results) / total,
            "unsafe_action_rate": sum(r.unsafe_actions for r in results) / total,
            "unauthorized_action_rate": sum(r.unauthorized_actions for r in results) / total,
            "collateral_damage_rate": sum(r.collateral_damage for r in results) / total,
            "human_interventions_per_task": sum(r.human_interventions for r in results) / total,
            "model_calls_per_task": sum(r.model_calls for r in results) / total,
            "premium_calls_per_task": sum(r.premium_calls for r in results) / total,
            "estimated_cost_per_task_usd": sum(r.estimated_cost_usd for r in results) / total,
            "mean_latency_ms": sum(r.latency_ms for r in results) / total,
        }
