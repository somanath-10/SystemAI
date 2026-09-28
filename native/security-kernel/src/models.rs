use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel { Observe, Low, Medium, High, Critical }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceScope {
    pub kind: String,
    pub value: String,
    #[serde(default)]
    pub recursive: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provenance {
    pub trust_class: String,
    pub source_type: String,
    pub source_resource: Option<String>,
    pub sensitivity: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionIntent {
    pub action_id: String,
    pub task_id: String,
    pub node_id: Option<String>,
    pub capability: String,
    #[serde(default)]
    pub parameters: serde_json::Value,
    #[serde(default)]
    pub resource_scope: Vec<ResourceScope>,
    pub risk_hint: Option<RiskLevel>,
    #[serde(default)]
    pub requires_confirmation: bool,
    #[serde(default)]
    pub requires_elevation: bool,
    #[serde(default)]
    pub provenance: Vec<Provenance>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityDefinition {
    pub name: String,
    pub risk: RiskLevel,
    pub executor: String,
    pub reversible: bool,
    #[serde(default)]
    pub dangerous: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthorizationDecision {
    pub decision: String,
    pub canonical_risk: RiskLevel,
    pub canonical_reversible: bool,
    pub approval_required: bool,
    pub reasons: Vec<String>,
}
