from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from systemai.contracts.models import (
    ActionIntent,
    AuthorizationResult,
    PolicyDecision,
    ResourceScope,
    RiskLevel,
)
from systemai.core.capabilities import CapabilityRegistry
from systemai.security.approvals import ApprovalStore
from systemai.security.provenance import provenance_constraints_for, requires_provenance_approval
from systemai.security.signing import CapabilitySigner


_RISK_RANK = {
    RiskLevel.OBSERVE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def max_risk(*risks: RiskLevel) -> RiskLevel:
    return max(risks, key=lambda r: _RISK_RANK[r])


@dataclass(slots=True)
class SecurityContext:
    actor_id: str
    session_id: str
    task_id: str
    executor_id: str
    device_id: str = "local"
    allowed_roots: tuple[Path, ...] = ()
    approval_id: str | None = None
    autonomy_mode: str = "assist"


class SecurityKernelV1:
    """Python reference/dev implementation of the V3 trusted kernel contract.

    The production repository also contains a Rust crate skeleton that owns this
    boundary in deployment. This Python implementation is intentionally strict so
    all V1 integration/evaluation tests can run in environments without Rust.
    """

    HARD_DENY_PREFIXES = (
        "security.bypass",
        "credential.extract",
        "credential.dump",
        "persistence.stealth",
        "surveillance.hidden",
    )

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        signer: CapabilitySigner,
        approvals: ApprovalStore,
    ) -> None:
        self.registry = registry
        self.signer = signer
        self.approvals = approvals

    def authorize(self, action: ActionIntent, context: SecurityContext) -> AuthorizationResult:
        if action.task_id != context.task_id:
            return AuthorizationResult(decision=self._deny("Action task does not match security context.", RiskLevel.CRITICAL, "task-binding"))
        if not self.registry.has(action.capability):
            return AuthorizationResult(decision=self._deny("Capability is not registered.", RiskLevel.HIGH, "unregistered-capability"))
        if action.capability.startswith(self.HARD_DENY_PREFIXES):
            return AuthorizationResult(decision=self._deny("Capability is outside the SystemAI authority model.", RiskLevel.CRITICAL, "hard-deny"))

        definition = self.registry.get(action.capability)
        hint = action.risk_hint or action.risk
        canonical_risk = max_risk(definition.risk, hint)
        canonical_reversible = self._canonical_reversibility(action)
        allowed_scope = self._scope(action, context)
        if allowed_scope is None:
            return AuthorizationResult(decision=self._deny("Action target is outside the task-authorized scope.", RiskLevel.HIGH, "scope-denied"))

        if action.requires_elevation:
            canonical_risk = max_risk(canonical_risk, RiskLevel.CRITICAL)

        approval_required = (
            action.requires_confirmation
            or action.requires_elevation
            or canonical_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
            or requires_provenance_approval(action)
            or (context.autonomy_mode == "assist" and canonical_risk not in {RiskLevel.OBSERVE, RiskLevel.LOW})
        )

        approval_id = context.approval_id
        if approval_required and not (approval_id and self.approvals.is_approved(approval_id, action_id=action.action_id)):
            if approval_id is None:
                approval_id = self.approvals.request(
                    action_id=action.action_id,
                    task_id=action.task_id,
                    requested_by=context.actor_id,
                    canonical_summary=self.canonical_summary(action, canonical_risk, canonical_reversible),
                    reason="Canonical policy requires user approval.",
                )
            decision = PolicyDecision(
                decision="require_approval",
                reason="Canonical policy requires explicit approval before this action.",
                risk=canonical_risk,
                canonical_reversible=canonical_reversible,
                policy_ids=["canonical-approval"],
                capability_token_required=True,
                required_isolation=self._required_isolation(action),
                allowed_scope=allowed_scope,
            )
            return AuthorizationResult(decision=decision, approval_id=approval_id)

        decision = PolicyDecision(
            decision="allow",
            reason="Action is registered, scoped, policy-compliant, and authorized.",
            risk=canonical_risk,
            canonical_reversible=canonical_reversible,
            policy_ids=["v1-canonical-policy"],
            capability_token_required=True,
            required_isolation=self._required_isolation(action),
            allowed_scope=allowed_scope,
        )
        token, _claims = self.signer.issue(
            action=action,
            session_id=context.session_id,
            executor_id=context.executor_id,
            device_id=context.device_id,
            approval_id=approval_id,
            provenance_constraints=provenance_constraints_for(action),
        )
        return AuthorizationResult(decision=decision, capability_token=token, approval_id=approval_id)

    def canonical_summary(self, action: ActionIntent, risk: RiskLevel, reversible: bool) -> str:
        target = action.target.model_dump(exclude_none=True) if action.target else {}
        parameters = json.dumps(self._approval_parameters(action.parameters), sort_keys=True, default=str)
        return (
            f"Capability: {action.capability}\n"
            f"Target: {target or '(none)'}\n"
            f"Parameters: {parameters}\n"
            f"Canonical risk: {risk.value}\n"
            f"Reversible: {'Yes' if reversible else 'No'}\n"
            f"Task: {action.task_id} / {action.node_id or '-'}\n"
            f"Reason: {action.expected_result}"
        )

    def _canonical_reversibility(self, action: ActionIntent) -> bool:
        definition = self.registry.get(action.capability)
        if not definition.reversible:
            return False
        if action.capability == "file.delete":
            return action.parameters.get("mode", "quarantine") in {"trash", "quarantine"}
        if action.capability == "process.terminate":
            return False
        if action.capability == "file.write":
            return bool(action.parameters.get("backup", True))
        return definition.reversible

    def _required_isolation(self, action: ActionIntent) -> str | None:
        if action.capability in {"sandbox.run", "test.run"}:
            return str(action.parameters.get("profile", "read_only"))
        if action.requires_elevation:
            return "approved_elevated_host_operation"
        return None

    def _scope(self, action: ActionIntent, context: SecurityContext) -> list[ResourceScope] | None:
        paths = [Path(scope.value) for scope in action.resource_scope if scope.kind == "filesystem"]
        if action.target and action.target.path:
            paths.append(Path(action.target.path))
        paths.extend(self._parameter_paths(action))
        if any(not self._path_allowed(path, context.allowed_roots) for path in paths):
            return None
        url = (action.target.url if action.target else None) or action.parameters.get("url")
        if action.capability == "http.health" and not self._local_health_url(url):
            return None
        if action.capability == "database.inspect" and str(action.parameters.get("host", "127.0.0.1")) not in {"127.0.0.1", "::1", "localhost"}:
            return None
        if action.resource_scope:
            return action.resource_scope
        if action.target and action.target.path:
            return [ResourceScope(kind="filesystem", value=action.target.path, recursive=False)]
        return []

    @staticmethod
    def _parameter_paths(action: ActionIntent) -> list[Path]:
        names = {
            "file.move": ("destination",),
            "process.start": ("cwd", "stdout_path", "stderr_path"),
            "sandbox.run": ("cwd",),
            "test.run": ("cwd",),
        }.get(action.capability, ())
        return [Path(str(action.parameters[name])).expanduser() for name in names if action.parameters.get(name)]

    @staticmethod
    def _local_health_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "::1", "localhost"}

    @classmethod
    def _approval_parameters(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "[redacted]" if any(marker in str(key).upper() for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY")) else cls._approval_parameters(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._approval_parameters(item) for item in value]
        return value

    @staticmethod
    def _path_allowed(path: Path, roots: tuple[Path, ...]) -> bool:
        if not roots:
            return True
        resolved = path.expanduser().resolve(strict=False)
        for root in roots:
            root_resolved = root.expanduser().resolve(strict=False)
            try:
                resolved.relative_to(root_resolved)
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _deny(reason: str, risk: RiskLevel, policy_id: str) -> PolicyDecision:
        return PolicyDecision(
            decision="deny",
            reason=reason,
            risk=risk,
            canonical_reversible=False,
            policy_ids=[policy_id],
            capability_token_required=False,
        )
