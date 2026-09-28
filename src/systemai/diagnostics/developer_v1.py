from __future__ import annotations

from pathlib import Path

from systemai.contracts.models import (
    ActionIntent,
    ActionTarget,
    DiagnosisReport,
    Hypothesis,
    ResourceScope,
    RiskLevel,
    SourceProvenance,
    TrustLevel,
    VerificationSpec,
)
from systemai.diagnostics.project_inspector import ProjectInspector, project_path


class DeveloperDiagnosisEngineV1:
    """Evidence-driven diagnosis for the first SystemAI product wedge."""

    def __init__(self, inspector: ProjectInspector | None = None) -> None:
        self.inspector = inspector or ProjectInspector()

    def diagnose(self, task_id: str, project_root: Path) -> DiagnosisReport:
        facts = self.inspector.inspect(project_root)
        root = Path(facts["project_root"])
        manifest = facts["manifest"]
        hypotheses: list[Hypothesis] = []
        actions: list[ActionIntent] = []

        if facts["manifest_issues"]:
            issues = "; ".join(facts["manifest_issues"])
            hypotheses.append(Hypothesis(code="unsafe_manifest", cause=issues, confidence=1.0, status="confirmed"))
            return DiagnosisReport(project_root=str(root), facts=facts, hypotheses=hypotheses, recommended_actions=[], summary="Project manifest requests paths or a health check outside the V1 local project boundary.")

        if facts["health"].get("ok"):
            hypotheses.append(Hypothesis(code="already_healthy", cause="Configured health endpoint is already healthy.", supporting_evidence=[str(facts["health"])], confidence=1.0, status="confirmed"))
            return DiagnosisReport(project_root=str(root), facts=facts, hypotheses=hypotheses, recommended_actions=[], summary="Project is already healthy; no repair is required.")

        missing_env = facts["env"].get("missing_keys") or []
        if missing_env:
            hypotheses.append(Hypothesis(code="missing_environment", cause=f"Required environment keys are missing: {', '.join(missing_env)}", supporting_evidence=[".env/.env.example shape inspection"], discriminating_test="Provide or configure missing values without exposing secrets.", confidence=0.98, status="confirmed"))
            # Do not invent secret values. V1 safely stops rather than guessing.
            return DiagnosisReport(project_root=str(root), facts=facts, hypotheses=hypotheses, recommended_actions=[], summary="Project cannot be safely repaired automatically because required environment values are missing.")

        listeners = facts["port"].get("listeners") or []
        expected_port = manifest.get("expected_port")
        if expected_port and listeners and not facts["health"].get("ok"):
            listener = listeners[0]
            hypotheses.append(Hypothesis(code="port_conflict", cause=f"Expected port {expected_port} is occupied while the configured health endpoint is unhealthy.", supporting_evidence=[str(listener), str(facts["health"])], discriminating_test="Terminate the explicitly identified conflicting process, then start the declared project command.", confidence=0.95, status="confirmed"))
            if listener.get("pid"):
                actions.append(
                    ActionIntent(
                        task_id=task_id,
                        node_id="repair-port-conflict",
                        capability="process.terminate",
                        target=ActionTarget(process_id=int(listener["pid"])),
                        parameters={"expected_create_time": listener.get("create_time"), "timeout": 5, "allow_kill": False},
                        expected_result=f"Process {listener['pid']} releases port {expected_port}",
                        verification=[VerificationSpec(kind="process.absent", parameters={"pid": int(listener["pid"])})],
                        expected_effects=[f"process:{listener['pid']}:terminated", f"port:{expected_port}:released"],
                        forbidden_effects=["terminate unrelated process"],
                        resource_scope=[ResourceScope(kind="process", value=str(listener["pid"])) , ResourceScope(kind="port", value=str(expected_port))],
                        risk_hint=RiskLevel.HIGH,
                        expected_reversibility=False,
                        requires_confirmation=True,
                        provenance=[SourceProvenance(trust_class=TrustLevel.TRUSTED, source_type="local_observation", source_resource=f"port:{expected_port}")],
                    )
                )

        if not manifest.get("start"):
            hypotheses.append(Hypothesis(code="missing_start_contract", cause="No explicit start command is available in the project manifest or auto-detection.", confidence=0.95, status="confirmed"))
            return DiagnosisReport(project_root=str(root), facts=facts, hypotheses=hypotheses, recommended_actions=[], summary="Diagnosis found the project is unhealthy, but no safe start command is declared; no repair action will run.")

        dependencies = {"repair-port-conflict"} if actions and actions[-1].node_id == "repair-port-conflict" else set()
        start_action = ActionIntent(
            task_id=task_id,
            node_id="start-project",
            capability="process.start",
            target=ActionTarget(path=str(root)),
            parameters={
                "argv": list(manifest["start"]),
                "cwd": str(project_path(root, manifest.get("cwd", "."))),
                "stdout_path": str(root / ".systemai" / "run.stdout.log"),
                "stderr_path": str(root / ".systemai" / "run.stderr.log"),
            },
            expected_result="Declared project process starts successfully.",
            verification=[VerificationSpec(kind="process.started_from_result"), *([VerificationSpec(kind="port.listening", parameters={"port": expected_port})] if expected_port else [])],
            expected_effects=["project process started"],
            forbidden_effects=["write outside project scope"],
            resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True), *([ResourceScope(kind="port", value=str(expected_port))] if expected_port else [])],
            risk_hint=RiskLevel.MEDIUM,
            expected_reversibility=True,
            provenance=[SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="project_manifest", source_resource=str(root / ".systemai" / "project.json"))],
        )
        actions.append(start_action)

        if manifest.get("health_url"):
            actions.append(
                ActionIntent(
                    task_id=task_id,
                    node_id="verify-health",
                    capability="http.health",
                    target=ActionTarget(url=manifest["health_url"]),
                    parameters={"url": manifest["health_url"], "timeout": 3.0},
                    expected_result="Configured health endpoint returns a healthy response.",
                    verification=[VerificationSpec(kind="http.status", parameters={"min": 200, "max": 399})],
                    expected_effects=["health endpoint healthy"],
                    resource_scope=[ResourceScope(kind="network", value=manifest["health_url"])],
                    risk_hint=RiskLevel.OBSERVE,
                    expected_reversibility=True,
                    provenance=[SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="project_manifest")],
                )
            )

        if manifest.get("test"):
            actions.append(
                ActionIntent(
                    task_id=task_id,
                    node_id="run-tests",
                    capability="test.run",
                    target=ActionTarget(path=str(root)),
                    parameters={"argv": list(manifest["test"]), "cwd": str(root), "profile": "read_only", "timeout": 120},
                    expected_result="Declared project tests pass.",
                    verification=[VerificationSpec(kind="command.exit_code", parameters={"equals": 0})],
                    resource_scope=[ResourceScope(kind="filesystem", value=str(root), recursive=True)],
                    risk_hint=RiskLevel.MEDIUM,
                    expected_reversibility=False,
                    provenance=[SourceProvenance(trust_class=TrustLevel.UNTRUSTED, source_type="project_manifest")],
                )
            )

        if not hypotheses:
            hypotheses.append(Hypothesis(code="process_not_running", cause="Project health check is unhealthy and no listener is present on the expected port.", supporting_evidence=[str(facts["health"]), str(facts["port"])], confidence=0.85, status="likely"))

        return DiagnosisReport(project_root=str(root), facts=facts, hypotheses=hypotheses, recommended_actions=actions, summary="Diagnosis produced a bounded remediation plan based on local project evidence.")
