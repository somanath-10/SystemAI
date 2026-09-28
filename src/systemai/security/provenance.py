from __future__ import annotations

from systemai.contracts.models import ActionIntent, Sensitivity, SourceProvenance, TrustLevel


SENSITIVE_CAPABILITY_PREFIXES = (
    "external.",
    "credential.",
    "file.delete",
    "process.terminate",
    "process.start",
    "sandbox.",
    "test.",
    "software.",
    "system.",
)


def effective_trust(items: list[SourceProvenance]) -> TrustLevel:
    if not items:
        return TrustLevel.TRUSTED
    trusts = {x.trust_class for x in items}
    if TrustLevel.UNTRUSTED in trusts and TrustLevel.TRUSTED in trusts:
        return TrustLevel.MIXED
    if TrustLevel.UNTRUSTED in trusts or TrustLevel.MIXED in trusts:
        return TrustLevel.UNTRUSTED if trusts == {TrustLevel.UNTRUSTED} else TrustLevel.MIXED
    return TrustLevel.TRUSTED


def highest_sensitivity(items: list[SourceProvenance]) -> Sensitivity:
    rank = {Sensitivity.PUBLIC: 0, Sensitivity.INTERNAL: 1, Sensitivity.SENSITIVE: 2, Sensitivity.SECRET: 3}
    if not items:
        return Sensitivity.INTERNAL
    return max((x.sensitivity for x in items), key=lambda v: rank[v])


def provenance_constraints_for(action: ActionIntent) -> list[str]:
    constraints: list[str] = []
    trust = effective_trust(action.provenance)
    sensitivity = highest_sensitivity(action.provenance)
    if trust != TrustLevel.TRUSTED:
        constraints.append("contains_untrusted_provenance")
    if sensitivity in {Sensitivity.SENSITIVE, Sensitivity.SECRET}:
        constraints.append(f"sensitivity:{sensitivity.value}")
    return constraints


def requires_provenance_approval(action: ActionIntent) -> bool:
    trust = effective_trust(action.provenance)
    return trust != TrustLevel.TRUSTED and action.capability.startswith(SENSITIVE_CAPABILITY_PREFIXES)
