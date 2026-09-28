from __future__ import annotations

from dataclasses import dataclass

from systemai.contracts.models import ActionIntent, ActionResult, VerificationResult, VerificationStatus


@dataclass(slots=True)
class RecoveryDecision:
    strategy: str
    reason: str
    retry: bool = False
    escalate_to: str | None = None


class RecoveryEngine:
    """Deterministic first-line recovery before invoking expensive AI replanning."""

    def decide(
        self,
        *,
        action: ActionIntent,
        verification: VerificationResult,
        attempts: int,
        max_attempts: int,
        result: ActionResult | None = None,
    ) -> RecoveryDecision:
        if verification.status == VerificationStatus.PASSED:
            return RecoveryDecision("none", "verification passed")

        driver_code = None
        if result is not None:
            driver_code = result.output.get("driver_error_code") if isinstance(result.output, dict) else None

        if driver_code in {"stale_element_token", "snapshot_id_required"}:
            return RecoveryDecision(
                "refresh_snapshot",
                "desktop element identity is stale; observe the exact window again before retrying",
                retry=False,
                escalate_to="planner",
            )

        if driver_code in {"window_target_not_found", "invalid_action_target"}:
            return RecoveryDecision(
                "re_resolve_target",
                "desktop target changed; re-enumerate apps/windows and rebuild the action target",
                retry=False,
                escalate_to="planner",
            )

        if attempts < max_attempts and action.reversible:
            return RecoveryDecision(
                "retry",
                "reversible action failed verification and retry budget remains",
                retry=True,
            )

        if action.capability.startswith("ui."):
            return RecoveryDecision(
                "visual_fallback",
                "semantic UI action failed; escalate to vision grounding",
                escalate_to="vision",
            )

        if action.capability.startswith("browser."):
            return RecoveryDecision(
                "desktop_fallback",
                "browser semantic action failed; consider desktop accessibility/vision fallback",
                escalate_to="computer",
            )

        return RecoveryDecision(
            "replan",
            "verification failed and deterministic retry/fallback was exhausted",
            escalate_to="planner",
        )
