from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from systemai.contracts.models import ActionIntent, PolicyDecision, RiskLevel
from systemai.core.capabilities import CapabilityRegistry


@dataclass(slots=True)
class PolicyContext:
    task_id: str
    user_id: str = "local-user"
    autonomous: bool = True
    allow_elevation: bool = False
    allowed_roots: list[Path] = field(default_factory=list)
    approved_action_ids: set[str] = field(default_factory=set)


class PolicyKernel:
    """Central authorization boundary.

    The reasoning model proposes actions; this class decides whether they may reach
    an executor. Untrusted content never bypasses this layer.
    """

    HARD_DENY_PREFIXES = (
        "security.bypass",
        "credential.extract",
        "credential.dump",
        "persistence.stealth",
        "surveillance.hidden",
    )

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def evaluate(self, action: ActionIntent, context: PolicyContext) -> PolicyDecision:
        capability = action.capability.lower()

        if capability.startswith(self.HARD_DENY_PREFIXES):
            return PolicyDecision(
                decision="deny",
                reason="Capability is outside the authorized SystemAI security model.",
                risk=RiskLevel.CRITICAL,
                policy_ids=["hard-deny-dangerous-capability"],
            )

        if not self.registry.has(capability):
            return PolicyDecision(
                decision="deny",
                reason="Capability is not registered.",
                risk=RiskLevel.HIGH,
                policy_ids=["deny-unregistered-capability"],
            )

        definition = self.registry.get(capability)
        effective_risk = max_risk(definition.risk, action.risk)

        scope_decision = self._check_path_scope(action, context)
        if scope_decision is not None:
            return scope_decision

        if action.requires_elevation and not context.allow_elevation:
            return PolicyDecision(
                decision="deny",
                reason="Task is not authorized to request privileged elevation.",
                risk=RiskLevel.CRITICAL,
                policy_ids=["deny-unapproved-elevation"],
            )

        if action.action_id in context.approved_action_ids:
            return PolicyDecision(
                decision="allow",
                reason="Action explicitly approved for this task.",
                risk=effective_risk,
                policy_ids=["explicit-action-approval"],
                capability_token_required=action.requires_elevation,
            )

        if action.requires_confirmation or effective_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return PolicyDecision(
                decision="require_approval",
                reason="Consequential or sensitive action requires explicit approval.",
                risk=effective_risk,
                policy_ids=["approval-for-high-risk"],
                capability_token_required=action.requires_elevation or effective_risk == RiskLevel.CRITICAL,
            )

        return PolicyDecision(
            decision="allow",
            reason="Action is registered and within the current task policy.",
            risk=effective_risk,
            policy_ids=["default-allow-bounded-capability"],
        )

    def _check_path_scope(self, action: ActionIntent, context: PolicyContext) -> PolicyDecision | None:
        if action.target is None or action.target.path is None:
            return None
        if not context.allowed_roots:
            return None

        raw = Path(action.target.path).expanduser()
        try:
            resolved = raw.resolve(strict=False)
        except OSError:
            resolved = raw.absolute()

        allowed = False
        for root in context.allowed_roots:
            root_resolved = root.expanduser().resolve(strict=False)
            try:
                resolved.relative_to(root_resolved)
                allowed = True
                break
            except ValueError:
                continue
        if allowed:
            return None
        return PolicyDecision(
            decision="deny",
            reason=f"Path is outside task-authorized roots: {resolved}",
            risk=RiskLevel.HIGH,
            policy_ids=["filesystem-scope-boundary"],
        )


_RISK_ORDER = {
    RiskLevel.OBSERVE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b
