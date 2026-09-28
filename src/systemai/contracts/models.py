from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskLevel(str, Enum):
    OBSERVE = "observe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"  # legacy-compatible transient state
    READY = "ready"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXECUTING = "executing"  # legacy-compatible umbrella state
    OBSERVING = "observing"
    RUNNING = "running"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    REPLANNING = "replanning"
    PAUSED = "paused"
    USER_TAKEOVER = "user_takeover"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepState(str, Enum):
    PENDING = "pending"
    CREATED = "created"
    READY = "ready"
    BLOCKED = "blocked"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    REPLANNING = "replanning"
    PAUSED = "paused"
    USER_TAKEOVER = "user_takeover"
    SUCCEEDED = "succeeded"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    ALLOWED = "allowed"
    DENIED = "denied"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class EffectStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNVERIFIABLE = "unverifiable"
    SUSPECTED_NOOP = "suspected_noop"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TrustLevel(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    MIXED = "mixed"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class ApprovalMode(str, Enum):
    NEVER = "never"
    POLICY = "policy"
    ALWAYS = "always"


class SandboxProfile(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE_NO_NETWORK = "workspace_write_no_network"
    WORKSPACE_WRITE_ALLOWLIST_NETWORK = "workspace_write_allowlist_network"
    TEMPORARY_CONTAINER_OR_VM = "temporary_container_or_vm"
    APPROVED_ELEVATED_HOST_OPERATION = "approved_elevated_host_operation"


class ActionJournalStatus(str, Enum):
    PREPARED = "prepared"
    AUTHORIZED = "authorized"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    EFFECT_OBSERVED = "effect_observed"
    VERIFIED = "verified"
    COMMIT_STATUS_UNKNOWN = "commit_status_unknown"
    REJECTED = "rejected"
    FAILED = "failed"


class SourceProvenance(BaseModel):
    trust_class: TrustLevel = TrustLevel.TRUSTED
    source_type: str = "user"
    source_resource: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    derived_from: list[str] = Field(default_factory=list)
    transformation_history: list[str] = Field(default_factory=list)


class ProvenanceValue(BaseModel):
    data: Any
    provenance: SourceProvenance = Field(default_factory=SourceProvenance)


class ResourceScope(BaseModel):
    kind: str
    value: str
    recursive: bool = False
    permissions: list[str] = Field(default_factory=list)


class BudgetProfile(BaseModel):
    max_cloud_spend_usd: float = 0.0
    max_cloud_calls: int = 0
    max_premium_calls: int = 0
    max_image_calls: int = 0
    max_audio_seconds: int = 0
    max_runtime_seconds: int = 900


class ApprovalPolicy(BaseModel):
    mode: ApprovalMode = ApprovalMode.POLICY
    require_for_high_risk: bool = True
    require_for_critical_risk: bool = True
    require_for_external_side_effects: bool = True


class GoalContract(BaseModel):
    goal_id: str = Field(default_factory=lambda: f"goal_{uuid4().hex[:16]}")
    objective: str
    constraints: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    forbidden_effects: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    resource_scope: list[ResourceScope] = Field(default_factory=list)
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    priority: int = 50
    privacy_profile: str = "local-first"
    budget_profile: BudgetProfile = Field(default_factory=BudgetProfile)
    actor_id: str = "local-user"
    session_id: str = Field(default_factory=lambda: f"session_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=utc_now)


class ActionTarget(BaseModel):
    application: str | None = None
    bundle_id: str | None = None
    window_id: str | None = None
    window_title: str | None = None
    element_id: str | None = None
    element_token: str | None = None
    element_role: str | None = None
    element_name: str | None = None
    path: str | None = None
    url: str | None = None
    process_id: int | None = None
    device_id: str | None = None
    display_id: str | None = None
    generation: str | None = None
    service_name: str | None = None
    port: int | None = None


class VerificationSpec(BaseModel):
    kind: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    description: str | None = None


class ActionIntent(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:16]}")
    task_id: str
    node_id: str | None = None
    capability: str
    target: ActionTarget | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_result: str
    verification: list[VerificationSpec] = Field(default_factory=list)
    expected_effects: list[str] = Field(default_factory=list)
    forbidden_effects: list[str] = Field(default_factory=list)
    resource_scope: list[ResourceScope] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.LOW  # legacy field, treated as planner hint only in kernel
    risk_hint: RiskLevel | None = None
    reversible: bool = True  # legacy/planner hint only
    expected_reversibility: bool | None = None
    requires_elevation: bool = False
    requires_confirmation: bool = False
    idempotency_key: str | None = None
    proposed_executor: str | None = None
    provenance: list[SourceProvenance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, value: str) -> str:
        if not value or "." not in value:
            raise ValueError("capability must be namespaced, e.g. 'file.read'")
        return value.strip().lower()


class ActionResult(BaseModel):
    action_id: str
    status: ActionStatus
    effect: EffectStatus = EffectStatus.UNVERIFIABLE
    executor: str
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    fallback_used: str | None = None
    side_effects: list[str] = Field(default_factory=list)
    duration_ms: float | None = None


class VerificationResult(BaseModel):
    action_id: str
    status: VerificationStatus
    checks: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    collateral_checks: list[dict[str, Any]] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    decision: Literal["allow", "deny", "require_approval"]
    reason: str
    risk: RiskLevel
    canonical_reversible: bool = False
    policy_ids: list[str] = Field(default_factory=list)
    capability_token_required: bool = True
    required_isolation: str | None = None
    allowed_scope: list[ResourceScope] = Field(default_factory=list)


class AuthorizationResult(BaseModel):
    decision: PolicyDecision
    capability_token: str | None = None
    approval_id: str | None = None


class ObservedContent(BaseModel):
    source: str
    trust: TrustLevel
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:16]}")
    source_type: str
    source_resource: str | None = None
    trust_class: TrustLevel = TrustLevel.UNTRUSTED
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    freshness: str | None = None
    generation: str | None = None
    content_hash: str | None = None
    structured_data: dict[str, Any] = Field(default_factory=dict)
    artifact_reference: str | None = None
    redactions: list[str] = Field(default_factory=list)
    provenance: SourceProvenance = Field(default_factory=lambda: SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="observation"))
    created_at: datetime = Field(default_factory=utc_now)


class SystemEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:16]}")
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trust: TrustLevel = TrustLevel.TRUSTED
    created_at: datetime = Field(default_factory=utc_now)


class CapabilityDefinition(BaseModel):
    name: str
    description: str
    risk: RiskLevel
    executor: str
    reversible: bool = True
    idempotent: bool = False
    retry_safe: bool = False
    supports_idempotency_key: bool = False
    compensation_strategy: str | None = None
    requires_permissions: list[str] = Field(default_factory=list)
    dangerous: bool = False
    aliases: list[str] = Field(default_factory=list)
    supported_verifiers: list[str] = Field(default_factory=list)
    resource_scope_model: str = "task"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ResourceLease(BaseModel):
    resource: str
    holder_task_id: str
    holder_node_id: str | None = None
    lease_id: str = Field(default_factory=lambda: f"lease_{uuid4().hex[:16]}")
    fencing_token: int = 0
    expires_at: datetime


class TaskRequest(BaseModel):
    goal: str
    user_id: str = "local-user"
    metadata: dict[str, Any] = Field(default_factory=dict)
    autonomous: bool = True


class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    reason: str | None = None


class CapabilityTokenClaims(BaseModel):
    version: int = 1
    key_id: str
    audience: str
    executor_id: str
    device_id: str
    session_id: str
    task_id: str
    node_id: str | None = None
    action_id: str
    action_hash: str
    capability_name: str
    resource_scope: list[ResourceScope] = Field(default_factory=list)
    parameter_hash: str
    approval_id: str | None = None
    provenance_constraints: list[str] = Field(default_factory=list)
    issued_at: datetime
    expires_at: datetime
    nonce: str
    max_uses: int = 1


class ProjectManifest(BaseModel):
    name: str = "project"
    runtime: str | None = None
    start: list[str] = Field(default_factory=list)
    test: list[str] = Field(default_factory=list)
    cwd: str = "."
    expected_port: int | None = None
    health_url: str | None = None
    required_env: list[str] = Field(default_factory=list)
    log_files: list[str] = Field(default_factory=list)
    service_names: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    code: str
    cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    discriminating_test: str | None = None
    test_cost: float = 0.0
    test_risk: RiskLevel = RiskLevel.OBSERVE
    confidence: float = 0.0
    status: str = "open"


class DiagnosisReport(BaseModel):
    project_root: str
    facts: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    recommended_actions: list[ActionIntent] = Field(default_factory=list)
    summary: str = ""
