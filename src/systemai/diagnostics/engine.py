from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class DiagnosticHypothesis:
    name: str
    description: str
    confidence: float
    probe_capabilities: list[str]
    evidence: list[dict[str, Any]]


class HypothesisGenerator(Protocol):
    async def generate(self, problem: str, context: dict[str, Any]) -> list[DiagnosticHypothesis]: ...


class DiagnosticEngine:
    """Orchestrates hypothesis -> probe -> evidence; executors remain policy-gated.

    The actual model-based hypothesis generator is intentionally injected so the
    diagnosis layer is independent of any LLM provider.
    """

    def __init__(self, generator: HypothesisGenerator) -> None:
        self.generator = generator

    async def hypotheses(self, problem: str, context: dict[str, Any]) -> list[DiagnosticHypothesis]:
        items = await self.generator.generate(problem, context)
        return sorted(items, key=lambda h: h.confidence, reverse=True)
