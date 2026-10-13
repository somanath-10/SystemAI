from __future__ import annotations

from pydantic import BaseModel, Field

from systemai.contracts.models import ActionIntent, RiskLevel, Sensitivity, TrustLevel, VerificationResult
from systemai.core.capabilities import CapabilityRegistry
from systemai.intelligence.confidence import evidence_confidence
from systemai.security.signing import action_hash, hash_payload


class SkillStep(BaseModel):
    capability: str
    parameters_template: dict = Field(default_factory=dict)
    expected_result: str


class SkillDefinition(BaseModel):
    name: str
    description: str
    version: int = 1
    inputs: dict[str, str] = Field(default_factory=dict)
    steps: list[SkillStep]
    success_count: int = 0
    source: str = "manual"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def upsert(self, skill: SkillDefinition) -> None:
        current = self._skills.get(skill.name)
        if current and skill.version < current.version:
            raise ValueError("cannot replace a skill with an older version")
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition:
        return self._skills[name]

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda s: s.name)


def preview_candidate(snapshot: dict, capabilities: CapabilityRegistry) -> dict:
    """Project a verified task into a non-executable skill candidate."""
    reasons: set[str] = set()
    steps = []
    if snapshot["state"] != "completed":
        reasons.add("task_not_completed")
    if not snapshot["steps"]:
        reasons.add("no_actions")
    for item in snapshot["steps"]:
        action = ActionIntent.model_validate(item["action"])
        verification = VerificationResult.model_validate(item["verification"]) if item.get("verification") else None
        evidence = evidence_confidence(action, verification)
        try:
            definition = capabilities.get(action.capability)
            risk = definition.risk
        except KeyError:
            risk = None
            reasons.add("unknown_capability")
        if item["state"] not in {"succeeded", "completed"}:
            reasons.add("step_not_succeeded")
        if evidence["score"] < 0.9:
            reasons.add("independent_evidence_missing")
        if risk not in {RiskLevel.OBSERVE, RiskLevel.LOW}:
            reasons.add("risk_above_low")
        if action.requires_elevation:
            reasons.add("elevation_required")
        if not action.provenance:
            reasons.add("provenance_missing")
        elif any(source.trust_class != TrustLevel.TRUSTED for source in action.provenance):
            reasons.add("untrusted_provenance")
        if any(source.sensitivity == Sensitivity.SECRET for source in action.provenance):
            reasons.add("secret_provenance")
        steps.append({
            "action_id": action.action_id,
            "action_hash": action_hash(action),
            "verification_hash": hash_payload(verification.model_dump(mode="json")) if verification else None,
            "capability": action.capability,
            "canonical_risk": risk.value if risk else "unknown",
            "evidence": evidence,
        })
    status = "reviewable" if not reasons else "blocked"
    return {
        "task_id": snapshot["task_id"],
        "candidate_hash": hash_payload({"task_id": snapshot["task_id"], "task_state": snapshot["state"], "status": status, "reasons": sorted(reasons), "steps": steps}),
        "status": status,
        "reasons": sorted(reasons),
        "steps": steps,
        "qualified": False,
        "replay_authorized": False,
    }
