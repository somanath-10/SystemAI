from __future__ import annotations

from systemai.contracts.models import ActionIntent, VerificationResult, VerificationStatus


def evidence_confidence(action: ActionIntent, verification: VerificationResult | None) -> dict:
    """A conservative evidence grade, never a model's self-reported certainty."""
    if verification is None:
        return {"score": 0.0, "basis": "not verified"}
    if verification.status == VerificationStatus.FAILED:
        return {"score": 0.0, "basis": "postcondition failed"}
    if verification.status != VerificationStatus.PASSED:
        return {"score": 0.2, "basis": "postcondition unknown"}
    if not action.verification:
        return {"score": 0.5, "basis": "executor effect only"}
    required = {spec.kind for spec in action.verification if spec.required}
    observed = {check.get("kind") for check in verification.checks if check.get("passed") is True}
    if not required.issubset(observed):
        return {"score": 0.2, "basis": "required evidence missing"}
    return {"score": 0.95, "basis": "independent required postconditions passed"}
