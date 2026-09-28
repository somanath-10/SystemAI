pub mod models;
pub mod policy;
pub mod token;

#[cfg(test)]
mod tests {
    use super::models::*;
    use super::policy::canonicalize;

    #[test]
    fn planner_cannot_lower_high_risk_capability() {
        let action = ActionIntent {
            action_id: "a1".into(), task_id: "t1".into(), node_id: None,
            capability: "process.terminate".into(), parameters: serde_json::json!({}),
            resource_scope: vec![], risk_hint: Some(RiskLevel::Low), requires_confirmation: false,
            requires_elevation: false, provenance: vec![],
        };
        let cap = CapabilityDefinition { name: "process.terminate".into(), risk: RiskLevel::High, executor: "process".into(), reversible: false, dangerous: true };
        let d = canonicalize(&action, &cap);
        assert_eq!(d.canonical_risk, RiskLevel::High);
        assert!(d.approval_required);
    }
}
