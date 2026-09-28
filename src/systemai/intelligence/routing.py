from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from systemai.contracts.models import RiskLevel
from systemai.cost import CostController


class InferenceTier(str, Enum):
    DETERMINISTIC = "deterministic"
    LOCAL_SMALL = "local_small"
    LOCAL_LLM = "local_llm"
    LOCAL_VLM = "local_vlm"
    SPECIALIST_API = "specialist_api"
    STANDARD_API = "standard_api"
    PREMIUM_API = "premium_api"


class Modality(str, Enum):
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    MULTIMODAL = "multimodal"


class RoutingRequest(BaseModel):
    task_id: str
    purpose: str
    modality: Modality = Modality.TEXT
    complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: RiskLevel = RiskLevel.LOW
    deterministic_available: bool = False
    cached_skill_available: bool = False
    local_small_available: bool = True
    local_llm_available: bool = True
    local_vlm_available: bool = False
    specialist_api_available: bool = False
    local_attempted: bool = False
    local_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_external_cost_usd: float = Field(default=0.01, ge=0.0)
    external_vision: bool = False
    external_audio_seconds: float = Field(default=0.0, ge=0.0)
    force_tier: InferenceTier | None = None


class RoutingDecision(BaseModel):
    tier: InferenceTier
    reason: str
    external: bool
    should_compress_context: bool = True
    max_context_fraction: float = Field(default=0.35, ge=0.05, le=1.0)


class LocalFirstModelRouter:
    """Deterministic local-first inference routing.

    The router itself does not call a model. That avoids paying a model merely to
    decide which model to use. It chooses the least expensive tier that can
    reasonably satisfy the request and only permits cloud escalation when the task
    budget allows it.
    """

    def __init__(
        self,
        cost: CostController,
        *,
        low_confidence_threshold: float = 0.62,
        premium_complexity_threshold: float = 0.82,
    ) -> None:
        self.cost = cost
        self.low_confidence_threshold = low_confidence_threshold
        self.premium_complexity_threshold = premium_complexity_threshold

    def route(self, request: RoutingRequest) -> RoutingDecision:
        if request.force_tier is not None:
            return self._forced(request)

        if request.deterministic_available:
            return RoutingDecision(
                tier=InferenceTier.DETERMINISTIC,
                reason="a deterministic capability can satisfy the request",
                external=False,
                max_context_fraction=0.1,
            )

        if request.cached_skill_available:
            return RoutingDecision(
                tier=InferenceTier.DETERMINISTIC,
                reason="a verified cached skill can execute without fresh model reasoning",
                external=False,
                max_context_fraction=0.1,
            )

        if request.modality in {Modality.VISION, Modality.MULTIMODAL} and request.local_vlm_available:
            if not self._local_failed(request):
                return RoutingDecision(
                    tier=InferenceTier.LOCAL_VLM,
                    reason="vision is required and a local VLM is available",
                    external=False,
                    max_context_fraction=0.25,
                )

        if request.complexity <= 0.28 and request.local_small_available and not self._local_failed(request):
            return RoutingDecision(
                tier=InferenceTier.LOCAL_SMALL,
                reason="routine classification/routing fits the small local model tier",
                external=False,
                max_context_fraction=0.18,
            )

        if request.local_llm_available and not self._local_failed(request):
            if request.complexity < self.premium_complexity_threshold and request.risk not in {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            }:
                return RoutingDecision(
                    tier=InferenceTier.LOCAL_LLM,
                    reason="normal reasoning can remain on-device",
                    external=False,
                    max_context_fraction=0.35,
                )

        external_ok, budget_reason = self.cost.can_use_external(
            request.task_id,
            estimated_cost_usd=request.estimated_external_cost_usd,
            vision=request.external_vision,
            audio_seconds=request.external_audio_seconds,
        )
        if external_ok:
            if request.specialist_api_available and request.modality in {Modality.AUDIO, Modality.VISION}:
                return RoutingDecision(
                    tier=InferenceTier.SPECIALIST_API,
                    reason="local path is insufficient; a specialist API is cheaper than a frontier general model",
                    external=True,
                    max_context_fraction=0.2,
                )
            if request.complexity >= self.premium_complexity_threshold or request.risk in {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            }:
                return RoutingDecision(
                    tier=InferenceTier.PREMIUM_API,
                    reason="high complexity/risk warrants the strongest configured reasoning tier",
                    external=True,
                    max_context_fraction=0.45,
                )
            return RoutingDecision(
                tier=InferenceTier.STANDARD_API,
                reason="local confidence/capability was insufficient and the task budget permits escalation",
                external=True,
                max_context_fraction=0.35,
            )

        # Budget exhaustion never grants authority. Fall back to the strongest
        # available local tier and let the caller decide whether to ask the user.
        if request.modality in {Modality.VISION, Modality.MULTIMODAL} and request.local_vlm_available:
            return RoutingDecision(
                tier=InferenceTier.LOCAL_VLM,
                reason=f"external escalation blocked: {budget_reason}; using local VLM",
                external=False,
            )
        if request.local_llm_available:
            return RoutingDecision(
                tier=InferenceTier.LOCAL_LLM,
                reason=f"external escalation blocked: {budget_reason}; using local LLM",
                external=False,
            )
        if request.local_small_available:
            return RoutingDecision(
                tier=InferenceTier.LOCAL_SMALL,
                reason=f"external escalation blocked: {budget_reason}; using local small model",
                external=False,
            )
        raise RuntimeError(f"no permitted inference tier available ({budget_reason})")

    def _forced(self, request: RoutingRequest) -> RoutingDecision:
        tier = request.force_tier
        assert tier is not None
        external = tier in {
            InferenceTier.SPECIALIST_API,
            InferenceTier.STANDARD_API,
            InferenceTier.PREMIUM_API,
        }
        if external:
            allowed, reason = self.cost.can_use_external(
                request.task_id,
                estimated_cost_usd=request.estimated_external_cost_usd,
                vision=request.external_vision,
                audio_seconds=request.external_audio_seconds,
            )
            if not allowed:
                raise RuntimeError(f"forced external tier is outside budget: {reason}")
        return RoutingDecision(
            tier=tier,
            reason="tier explicitly forced by trusted configuration",
            external=external,
        )

    def _local_failed(self, request: RoutingRequest) -> bool:
        return (
            request.local_attempted
            and request.local_confidence is not None
            and request.local_confidence < self.low_confidence_threshold
        )
