use crate::models::{ActionIntent, AuthorizationDecision, CapabilityDefinition, RiskLevel};

pub fn max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel { if a >= b { a } else { b } }

pub fn canonicalize(action: &ActionIntent, capability: &CapabilityDefinition) -> AuthorizationDecision {
    let hinted = action.risk_hint.clone().unwrap_or(RiskLevel::Low);
    let mut risk = max_risk(capability.risk.clone(), hinted);
    let mut reasons = vec!["registered-capability".to_string()];
    if action.requires_elevation {
        risk = RiskLevel::Critical;
        reasons.push("elevation".to_string());
    }
    let untrusted = action.provenance.iter().any(|p| p.trust_class != "trusted");
    let sensitive_capability = action.capability.starts_with("external.")
        || action.capability == "process.terminate"
        || action.capability == "process.start"
        || action.capability.starts_with("sandbox.")
        || action.capability.starts_with("test.")
        || action.capability.starts_with("system.")
        || action.capability.starts_with("software.");
    if untrusted && sensitive_capability {
        reasons.push("untrusted-provenance".to_string());
    }
    let approval_required = action.requires_confirmation
        || matches!(risk, RiskLevel::High | RiskLevel::Critical)
        || (untrusted && sensitive_capability);
    AuthorizationDecision {
        decision: if approval_required { "require_approval" } else { "allow" }.to_string(),
        canonical_risk: risk,
        canonical_reversible: capability.reversible && action.capability != "process.terminate",
        approval_required,
        reasons,
    }
}
