from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from systemai.contracts.models import (
    ActionIntent,
    ActionJournalStatus,
    ActionResult,
    ActionTarget,
    GoalContract,
    ResourceScope,
    RiskLevel,
    StepState,
    TaskState,
    VerificationResult,
    VerificationSpec,
    VerificationStatus,
)
from systemai.core.task_graph import TaskGraph, TaskNode
from systemai.desktop import DesktopControlService
from systemai.execution.browser import PlaywrightExecutor
from systemai.security.origin import browser_origin
from systemai.execution.base import ExecutionGateway
from systemai.orchestration.action_journal import ActionJournal
from systemai.orchestration.event_store import EventStore
from systemai.orchestration.leases import ResourceBusy, ResourceLeaseManager
from systemai.planner.developer import DeveloperDiagnosisPlanner
from systemai.security.kernel import SecurityContext, SecurityKernel
from systemai.verification.postcondition import PostconditionVerifier


def _token_nonce(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload_b64 = token.split(".", 2)[1]
        payload = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        return json.loads(payload).get("nonce")
    except Exception:
        return None


@dataclass(slots=True)
class TaskSession:
    task_id: str
    contract: GoalContract
    project_root: Path
    graph: TaskGraph
    diagnosis: dict[str, Any]
    autonomy_mode: str = "standard_auto"
    state: TaskState = TaskState.READY
    results: dict[str, ActionResult] = field(default_factory=dict)
    verifications: dict[str, VerificationResult] = field(default_factory=dict)
    pending_approvals: dict[str, str] = field(default_factory=dict)  # action_id -> approval_id
    error: str | None = None
    requested_control: TaskState | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.contract.model_dump(mode="json"),
            "project_root": str(self.project_root),
            "autonomy_mode": self.autonomy_mode,
            "state": self.state.value,
            "error": self.error,
            "diagnosis": self.diagnosis,
            "pending_approvals": self.pending_approvals,
            "steps": [
                {
                    "node_id": n.node_id,
                    "title": n.title,
                    "state": n.state.value,
                    "dependencies": sorted(n.dependencies),
                    "resources": sorted(n.resource_requirements),
                    "attempts": n.attempts,
                    "max_attempts": n.max_attempts,
                    "last_error": n.last_error,
                    "action": n.action.model_dump(mode="json"),
                    "result": self.results.get(n.action.action_id).model_dump(mode="json") if n.action.action_id in self.results else None,
                    "verification": self.verifications.get(n.action.action_id).model_dump(mode="json") if n.action.action_id in self.verifications else None,
                }
                for n in self.graph.nodes.values()
            ],
        }


class SystemAIRuntime:
    """Event-sourced developer diagnosis runtime.

    SystemAI deliberately uses one planner plus specialized deterministic tools. Every
    consequential action passes through canonical policy, a signed capability,
    crash-safe journal, resource leases, a trusted executor, and an independent
    verifier.
    """

    def __init__(
        self,
        *,
        planner: DeveloperDiagnosisPlanner,
        security_kernel: SecurityKernel,
        gateway: ExecutionGateway,
        verifier: PostconditionVerifier,
        desktop: DesktopControlService | None = None,
        browser: PlaywrightExecutor | None = None,
        data_dir: Path | None = None,
        allowed_applications: set[str] | None = None,
        store: EventStore,
        journal: ActionJournal,
        leases: ResourceLeaseManager,
        autonomy_mode: str = "standard_auto",
    ) -> None:
        self.planner = planner
        self.security_kernel = security_kernel
        self.gateway = gateway
        self.verifier = verifier
        self.desktop = desktop
        self.browser = browser
        self.data_dir = data_dir
        self.allowed_applications = allowed_applications or set()
        self.store = store
        self.journal = journal
        self.leases = leases
        self.autonomy_mode = autonomy_mode
        self.sessions: dict[str, TaskSession] = {}

    async def create_developer_task(
        self,
        goal: str,
        project_root: Path,
        *,
        actor_id: str = "local-user",
        autonomy_mode: str | None = None,
    ) -> TaskSession:
        project_root = Path(project_root).expanduser().resolve(strict=True)
        autonomy_mode = autonomy_mode or self.autonomy_mode
        if autonomy_mode not in {"observe", "assist", "standard_auto"}:
            raise ValueError(f"unsupported autonomy mode: {autonomy_mode}")
        task_id = f"task_{uuid4().hex[:16]}"
        contract = self.planner.goal_contract(goal, project_root, actor_id=actor_id)
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        graph, report = await asyncio.to_thread(self.planner.plan, task_id=task_id, contract=contract, project_root=project_root)
        diagnosis = report.model_dump(mode="json")
        diagnosis["facts"] = self._redacted_facts(diagnosis.get("facts", {}))
        self.store.append("ObservationReceived", {"kind": "developer_diagnosis", "summary": report.summary, "facts": diagnosis["facts"]}, task_id=task_id)
        self.store.append("PlanCreated", {"nodes": graph.topological_order() if graph.nodes else [], "diagnosis": report.summary}, task_id=task_id)
        session = TaskSession(
            task_id=task_id,
            contract=contract,
            project_root=project_root,
            graph=graph,
            diagnosis=diagnosis,
            autonomy_mode=autonomy_mode,
        )
        self.sessions[task_id] = session
        self._persist(session)
        if not graph.nodes:
            if any(h.get("code") == "already_healthy" for h in diagnosis.get("hypotheses", [])):
                session.state = TaskState.COMPLETED
                self.store.append("TaskCompleted", {"reason": "already healthy"}, task_id=task_id)
            else:
                session.state = TaskState.FAILED
                session.error = report.summary
                self.store.append("TaskFailed", {"reason": report.summary}, task_id=task_id)
            self._persist(session)
            return session
        await self.run(task_id)
        return session

    async def create_desktop_observation(self) -> TaskSession:
        if self.desktop is None:
            raise RuntimeError("desktop driver is unavailable")
        status = await self.desktop.status()
        if not status.available:
            raise RuntimeError("desktop driver is unavailable")
        task_id = f"task_{uuid4().hex[:16]}"
        contract = GoalContract(objective="Inspect running desktop applications")
        action = ActionIntent(
            task_id=task_id,
            node_id="observe-apps",
            capability="application.list",
            expected_result="Running applications are observed",
            risk=RiskLevel.OBSERVE,
            verification=[VerificationSpec(kind="desktop.apps_observed")],
        )
        graph = TaskGraph.from_nodes(task_id, [TaskNode(node_id="observe-apps", title="Inspect applications", action=action, max_attempts=1)])
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        self.store.append("PlanCreated", {"nodes": ["observe-apps"]}, task_id=task_id)
        session = TaskSession(task_id=task_id, contract=contract, project_root=Path.cwd(), graph=graph, diagnosis={"summary": "Desktop observation"})
        self.sessions[task_id] = session
        self._persist(session)
        await self.run(task_id)
        return session

    async def create_desktop_task(
        self,
        *,
        capability: str,
        bundle_id: str,
        window_title: str | None = None,
        element_name: str | None = None,
        element_role: str | None = None,
        value: str | None = None,
        verify_element_name: str | None = None,
        verify_window_title: str | None = None,
    ) -> TaskSession:
        if self.desktop is None:
            raise RuntimeError("desktop driver is unavailable")
        status = await self.desktop.status()
        if not status.available:
            raise RuntimeError("desktop driver is unavailable")
        if bundle_id.casefold() not in {item.casefold() for item in self.allowed_applications}:
            raise ValueError("application is outside the configured desktop allowlist")
        supported = {"application.launch", "window.observe", "ui.click", "ui.set_value"}
        if capability not in supported:
            raise ValueError("unsupported desktop capability")
        if capability != "application.launch" and not window_title:
            raise ValueError("desktop action requires an exact window title")
        if capability in {"window.observe", "ui.click", "ui.set_value"} and (not status.permissions or status.permissions.accessibility is not True):
            raise RuntimeError("desktop Accessibility permission is not granted")
        if capability in {"ui.click", "ui.set_value"} and not (element_name or element_role):
            raise ValueError("UI action requires an element name or role")
        if capability == "ui.click" and not (verify_element_name or verify_window_title):
            raise ValueError("ui.click requires a fresh, verifiable postcondition")
        if capability == "ui.set_value" and value is None:
            raise ValueError("ui.set_value requires a value")
        task_id = f"task_{uuid4().hex[:16]}"
        target = ActionTarget(bundle_id=bundle_id, window_title=window_title, element_name=element_name, element_role=element_role)
        params: dict[str, Any] = {}
        verify_target = {"bundle_id": bundle_id, "window_title": window_title}
        specs: list[VerificationSpec]
        if capability == "application.launch":
            specs = [VerificationSpec(kind="application.running", parameters={"bundle_id": bundle_id})]
        elif capability == "window.observe":
            params["include_screenshot"] = False
            specs = [VerificationSpec(kind="window.exists", parameters=verify_target)]
        elif capability == "ui.set_value":
            executor = self.gateway.resolve(capability)
            if not hasattr(executor, "stash_value"):
                raise RuntimeError("authorized desktop executor is unavailable")
            assert value is not None
            params["value_ref"] = executor.stash_value(value)
            params["value_sha256"] = hashlib.sha256(value.encode()).hexdigest()
            specs = [VerificationSpec(kind="ui.element_value_sha256", parameters={
                **verify_target, "label": element_name, "role": element_role, "sha256": params["value_sha256"],
            })]
        elif verify_element_name:
            specs = [VerificationSpec(kind="ui.element_exists", parameters={**verify_target, "label": verify_element_name})]
        else:
            specs = [VerificationSpec(kind="window.exists", parameters={"bundle_id": bundle_id, "window_title": verify_window_title})]
        action = ActionIntent(
            task_id=task_id,
            node_id="desktop-action",
            capability=capability,
            target=target,
            parameters=params,
            expected_result=f"{capability} verified in {bundle_id}",
            verification=specs,
            resource_scope=[ResourceScope(kind="application", value=bundle_id)],
            risk=RiskLevel.LOW,
        )
        graph = TaskGraph.from_nodes(task_id, [TaskNode(
            node_id="desktop-action", title=capability.replace(".", " "), action=action,
            resource_requirements={"desktop:session"}, max_attempts=1,
        )])
        contract = GoalContract(objective=f"{capability} in {bundle_id}")
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        self.store.append("PlanCreated", {"nodes": ["desktop-action"]}, task_id=task_id)
        session = TaskSession(task_id=task_id, contract=contract, project_root=self.data_dir or Path.cwd(), graph=graph, diagnosis={"summary": "Desktop action"})
        self.sessions[task_id] = session
        self._persist(session)
        await self.run(task_id)
        return session

    async def create_browser_task(
        self,
        *,
        capability: str,
        url: str,
        selector: str | None = None,
        role: str | None = None,
        name: str | None = None,
        value: str | None = None,
        path: str | None = None,
        expected_url: str | None = None,
        expected_title: str | None = None,
        expected_text: str | None = None,
    ) -> TaskSession:
        if self.browser is None or not self.browser.status()["available"] or self.data_dir is None:
            raise RuntimeError("browser is not configured or Playwright is unavailable")
        self.browser.require_origin(url)
        if expected_url:
            self.browser.require_origin(expected_url)
        if capability not in self.browser.CAPABILITIES:
            raise ValueError("unsupported browser capability")
        if capability != "browser.navigate" and not (selector or name):
            raise ValueError("browser action requires a semantic target or selector")
        if capability == "browser.click" and not (expected_url or expected_title or expected_text):
            raise ValueError("browser.click requires a verifiable postcondition")
        if capability == "browser.fill" and value is None:
            raise ValueError("browser.fill requires a value")
        if capability == "browser.upload" and not path:
            raise ValueError("browser.upload requires a file path")
        if capability == "browser.observe" and (selector or name):
            raise ValueError("browser.observe inspects the current page, not an element")
        task_id = f"task_{uuid4().hex[:16]}"
        parameters: dict[str, Any] = {"url": url}
        if selector:
            parameters["selector"] = selector
        if role:
            parameters["role"] = role
        if name:
            parameters["name"] = name
        specs: list[VerificationSpec] = []
        scopes = [ResourceScope(kind="browser_origin", value=browser_origin(url))]
        root = self.data_dir
        if capability == "browser.navigate":
            specs.append(VerificationSpec(kind="browser.url_equals", parameters={"url": expected_url or url}))
            specs.append(VerificationSpec(kind="http.status", parameters={"min": 200, "max": 399}))
        elif capability == "browser.observe":
            specs.append(VerificationSpec(kind="browser.url_equals", parameters={"url": url}))
        elif capability == "browser.fill":
            assert value is not None
            parameters["value_ref"] = self.browser.stash_value(value)
            parameters["value_sha256"] = hashlib.sha256(value.encode()).hexdigest()
            specs.append(VerificationSpec(kind="browser.value_sha256", parameters={"sha256": parameters["value_sha256"]}))
        elif capability == "browser.download":
            assert self.browser.download_dir is not None
            scopes.append(ResourceScope(kind="filesystem", value=str(self.browser.download_dir), recursive=True))
            specs.append(VerificationSpec(kind="browser.download_sha256"))
            root = self.browser.download_dir
        elif capability == "browser.upload":
            upload = Path(str(path)).expanduser().resolve(strict=True)
            if not upload.is_file():
                raise ValueError("browser upload path must be a file")
            parameters["path"] = str(upload)
            scopes.append(ResourceScope(kind="filesystem", value=str(upload)))
            specs.append(VerificationSpec(kind="browser.upload_selected"))
            root = upload
        if expected_url and capability != "browser.navigate":
            specs.append(VerificationSpec(kind="browser.url_equals", parameters={"url": expected_url}))
        if expected_title:
            specs.append(VerificationSpec(kind="browser.title_equals", parameters={"title": expected_title}))
        if expected_text:
            specs.append(VerificationSpec(kind="browser.text_visible", parameters={"text": expected_text}))
        action = ActionIntent(
            task_id=task_id,
            node_id="browser-action",
            capability=capability,
            target=ActionTarget(url=url, element_name=name),
            parameters=parameters,
            expected_result=f"{capability} verified at {url}",
            verification=specs,
            resource_scope=scopes,
            risk=RiskLevel.OBSERVE if capability == "browser.observe" else RiskLevel.LOW,
        )
        graph = TaskGraph.from_nodes(task_id, [TaskNode(
            node_id="browser-action", title=capability.replace("browser.", "Browser ").replace("_", " "),
            action=action, resource_requirements={"browser:profile"}, max_attempts=1,
        )])
        contract = GoalContract(objective=f"{capability} at {url}")
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        self.store.append("PlanCreated", {"nodes": ["browser-action"]}, task_id=task_id)
        session = TaskSession(task_id=task_id, contract=contract, project_root=root, graph=graph, diagnosis={"summary": "Browser action"})
        self.sessions[task_id] = session
        self._persist(session)
        await self.run(task_id)
        return session

    async def run(self, task_id: str) -> TaskSession:
        session = self.sessions[task_id]
        async with session.lock:
            if session.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.PAUSED, TaskState.USER_TAKEOVER}:
                return session
            session.state = TaskState.RUNNING
            self._persist(session)
            while True:
                if session.requested_control is not None:
                    session.state = session.requested_control
                    self._persist(session)
                    return session
                ready = session.graph.ready_nodes()
                if not ready:
                    if session.graph.successful():
                        session.state = TaskState.COMPLETED
                        self.store.append("TaskCompleted", {"verified": True}, task_id=task_id)
                    elif session.graph.terminal():
                        session.state = TaskState.FAILED
                        session.error = "one or more DAG nodes failed"
                        self.store.append("TaskFailed", {"reason": session.error}, task_id=task_id)
                    self._persist(session)
                    return session
                node = sorted(ready, key=lambda x: x.node_id)[0]
                outcome = await self._run_node(session, node)
                if session.requested_control is not None:
                    session.state = session.requested_control
                self._persist(session)
                if session.requested_control is not None:
                    return session
                if outcome in {"waiting", "paused"}:
                    return session
                if outcome == "failed":
                    for descendant in session.graph.descendants(node.node_id):
                        candidate = session.graph.nodes[descendant]
                        if candidate.state in {StepState.PENDING, StepState.READY, StepState.BLOCKED}:
                            candidate.state = StepState.SKIPPED
                    continue

    async def _run_node(self, session: TaskSession, node: TaskNode) -> str:
        action = node.action
        leases = []
        try:
            try:
                leases = self.leases.acquire_many(node.resource_requirements, task_id=session.task_id, node_id=node.node_id, ttl_seconds=max(30, node.time_budget_seconds + 30))
            except ResourceBusy as exc:
                node.state = StepState.WAITING_FOR_RESOURCE
                node.last_error = str(exc)
                session.state = TaskState.WAITING_FOR_RESOURCE
                self.store.append("TaskNodeWaitingForResource", {"reason": str(exc)}, task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
                return "paused"

            node.state = StepState.RUNNING
            node.attempts += 1
            journal_state = self.journal.get(action.action_id)
            if journal_state is None or journal_state.get("status") == ActionJournalStatus.FAILED.value:
                self.journal.prepare(action)
            elif journal_state.get("status") == ActionJournalStatus.COMMIT_STATUS_UNKNOWN.value:
                node.state = StepState.FAILED
                node.last_error = "external side-effect commit status is unknown; reconcile before retry"
                return "failed"

            executor = self.gateway.resolve(action.capability)
            approval_id = session.pending_approvals.get(action.action_id)
            sec = self.security_kernel.authorize(
                action,
                SecurityContext(
                    actor_id=session.contract.actor_id,
                    session_id=session.contract.session_id,
                    task_id=session.task_id,
                    executor_id=executor.name,
                    allowed_roots=(session.project_root,),
                    allowed_browser_origins=tuple(self.browser.allowed_origins) if self.browser else (),
                    allowed_applications=tuple(self.allowed_applications),
                    approval_id=approval_id,
                    autonomy_mode=session.autonomy_mode,
                ),
            )
            self.store.append("PolicyDecision", sec.decision.model_dump(mode="json"), task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
            if sec.decision.decision == "deny":
                node.state = StepState.FAILED
                node.last_error = sec.decision.reason
                self.journal.transition(action, ActionJournalStatus.REJECTED, detail={"reason": sec.decision.reason})
                return "failed"
            if sec.decision.decision == "require_approval":
                if not sec.approval_id:
                    raise RuntimeError("approval required but no approval record was created")
                session.pending_approvals[action.action_id] = sec.approval_id
                node.state = StepState.WAITING_FOR_APPROVAL
                session.state = TaskState.WAITING_FOR_APPROVAL
                self.store.append("ApprovalRequested", {"approval_id": sec.approval_id, "canonical_summary": self.security_kernel.approvals.get(sec.approval_id)["canonical_summary"]}, task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
                return "waiting"

            token = sec.capability_token
            self.journal.transition(action, ActionJournalStatus.AUTHORIZED, token_nonce=_token_nonce(token))
            self.journal.transition(action, ActionJournalStatus.DISPATCHING)
            self.store.append("ActionDispatchStarted", {"executor": executor.name}, task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
            try:
                result = await self.gateway.execute(action, capability_token=token)
            except Exception as exc:
                result = ActionResult(action_id=action.action_id, status="failed", effect="failed", executor=executor.name, error=f"{type(exc).__name__}: {exc}")
            session.results[action.action_id] = result
            self.journal.transition(action, ActionJournalStatus.DISPATCHED, result=result)
            self.store.append("ActionDispatched", result.model_dump(mode="json"), task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
            if result.status.value != "completed":
                self.journal.transition(action, ActionJournalStatus.FAILED, result=result, detail={"error": result.error})
                return await self._maybe_retry(session, node, "executor failed")

            self.journal.transition(action, ActionJournalStatus.EFFECT_OBSERVED, result=result)
            node.state = StepState.VERIFYING
            session.state = TaskState.VERIFYING
            verification = await self.verifier.verify(action, result)
            session.verifications[action.action_id] = verification
            self.store.append("ObservationReceived", {"executor_output": result.output}, task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
            self.store.append("VerificationPassed" if verification.status == VerificationStatus.PASSED else "VerificationFailed", verification.model_dump(mode="json"), task_id=session.task_id, node_id=node.node_id, action_id=action.action_id)
            with self.store.connect() as c:
                c.execute("INSERT OR REPLACE INTO verification_results(action_id,result_json,created_at) VALUES(?,?,datetime('now'))", (action.action_id, json.dumps(verification.model_dump(mode="json"), sort_keys=True)))
            if verification.status == VerificationStatus.PASSED:
                self.journal.transition(action, ActionJournalStatus.VERIFIED)
                node.state = StepState.SUCCEEDED
                session.state = TaskState.RUNNING
                session.pending_approvals.pop(action.action_id, None)
                return "succeeded"
            self.journal.transition(action, ActionJournalStatus.FAILED, detail={"summary": verification.summary})
            return await self._maybe_retry(session, node, verification.summary)
        finally:
            self.leases.release_many(leases)

    async def _maybe_retry(self, session: TaskSession, node: TaskNode, error: str) -> str:
        node.last_error = error
        if node.attempts < node.max_attempts and self.security_kernel.registry.get(node.action.capability).retry_safe:
            node.state = StepState.PENDING
            session.state = TaskState.RECOVERING
            self.store.append("RecoveryStarted", {"strategy": "safe_retry", "attempt": node.attempts, "reason": error}, task_id=session.task_id, node_id=node.node_id, action_id=node.action.action_id)
            await asyncio.sleep(min(0.25 * node.attempts, 1.0))
            session.state = TaskState.RUNNING
            return "retry"
        node.state = StepState.FAILED
        session.state = TaskState.RUNNING
        return "failed"

    def approve(self, task_id: str, action_id: str, *, approved: bool, approved_by: str = "local-user", reason: str | None = None) -> str:
        session = self.sessions[task_id]
        if session.state in {TaskState.CANCELLED, TaskState.USER_TAKEOVER}:
            raise ValueError("task is no longer accepting approvals")
        approval_id = session.pending_approvals.get(action_id)
        if not approval_id:
            raise KeyError("action is not awaiting approval")
        self.security_kernel.approvals.decide(approval_id, approved=approved, approved_by=approved_by, reason=reason)
        self.store.append("ApprovalGranted" if approved else "ApprovalDenied", {"approval_id": approval_id, "approved_by": approved_by, "reason": reason}, task_id=task_id, action_id=action_id)
        node = next(n for n in session.graph.nodes.values() if n.action.action_id == action_id)
        if approved:
            node.state = StepState.PENDING
            if session.state != TaskState.PAUSED:
                session.state = TaskState.READY
        else:
            node.state = StepState.FAILED
            node.last_error = reason or "approval denied"
            session.state = TaskState.FAILED
            session.error = node.last_error
            if self.browser and node.action.capability == "browser.fill":
                self.browser.forget_value(str(node.action.parameters.get("value_ref", "")))
            if node.action.capability == "ui.set_value":
                executor = self.gateway.resolve(node.action.capability)
                if hasattr(executor, "forget_value"):
                    executor.forget_value(str(node.action.parameters.get("value_ref", "")))
        self._persist(session)
        return approval_id

    def pause(self, task_id: str) -> None:
        session = self.sessions[task_id]
        session.requested_control = TaskState.PAUSED
        session.state = TaskState.PAUSED
        self.store.append("TaskPaused", {}, task_id=task_id)
        self._persist(session)

    def take_control(self, task_id: str) -> None:
        session = self.sessions[task_id]
        self._forget_browser_values(session)
        session.requested_control = TaskState.USER_TAKEOVER
        session.state = TaskState.USER_TAKEOVER
        self.store.append("UserTakeover", {}, task_id=task_id)
        self._persist(session)

    def cancel(self, task_id: str) -> None:
        session = self.sessions[task_id]
        self._forget_browser_values(session)
        session.requested_control = TaskState.CANCELLED
        session.state = TaskState.CANCELLED
        self.store.append("TaskCancelled", {}, task_id=task_id)
        self._persist(session)

    async def resume(self, task_id: str) -> TaskSession:
        session = self.sessions[task_id]
        if session.state not in {TaskState.PAUSED, TaskState.WAITING_FOR_RESOURCE}:
            raise ValueError("task is not paused or waiting for a resource")
        if any(
            (journal := self.journal.get(node.action.action_id))
            and journal["status"] == ActionJournalStatus.COMMIT_STATUS_UNKNOWN.value
            for node in session.graph.nodes.values()
        ):
            raise ValueError("manual reconciliation is required for an interrupted action")
        for node in session.graph.nodes.values():
            if node.state == StepState.WAITING_FOR_RESOURCE:
                node.state = StepState.PENDING
        session.requested_control = None
        if self._has_undecided_approvals(session):
            session.state = TaskState.WAITING_FOR_APPROVAL
            self._persist(session)
            return session
        session.state = TaskState.READY
        self.store.append("TaskResumed", {}, task_id=task_id)
        self._persist(session)
        return await self.run(task_id)

    def restore_sessions(self) -> list[str]:
        """Rehydrate durable snapshots without replaying an interrupted side effect."""
        self.reconcile_unresolved_actions()
        restored: list[str] = []
        for record in self.store.task_snapshots():
            snapshot = record["snapshot"]
            try:
                nodes = [
                    TaskNode(
                        node_id=step["node_id"],
                        title=step["title"],
                        action=self._action_from_snapshot(step["action"]),
                        dependencies=set(step.get("dependencies", [])),
                        resource_requirements=set(step.get("resources", [])),
                        state=StepState(step["state"]),
                        attempts=int(step.get("attempts", 0)),
                        max_attempts=int(step.get("max_attempts", 2)),
                        last_error=step.get("last_error"),
                    )
                    for step in snapshot["steps"]
                ]
                graph = TaskGraph.from_nodes(record["task_id"], nodes)
                session = TaskSession(
                    task_id=record["task_id"],
                    contract=GoalContract.model_validate(snapshot["goal"]),
                    project_root=Path(snapshot["project_root"]),
                    graph=graph,
                    diagnosis=snapshot["diagnosis"],
                    autonomy_mode=snapshot.get("autonomy_mode", self.autonomy_mode),
                    state=TaskState(snapshot["state"]),
                    pending_approvals=dict(snapshot.get("pending_approvals", {})),
                    error=snapshot.get("error"),
                )
                for step in snapshot["steps"]:
                    action_id = step["action"]["action_id"]
                    if step.get("result"):
                        session.results[action_id] = ActionResult.model_validate(step["result"])
                    if step.get("verification"):
                        session.verifications[action_id] = VerificationResult.model_validate(step["verification"])
                unsafe = [
                    node
                    for node in graph.nodes.values()
                    if (journal := self.journal.get(node.action.action_id))
                    and journal["status"] == ActionJournalStatus.COMMIT_STATUS_UNKNOWN.value
                ]
                if unsafe:
                    for node in unsafe:
                        node.state = StepState.FAILED
                        node.last_error = "action commit status is unknown after restart; inspect external state before replanning"
                    session.state = TaskState.PAUSED
                    session.error = "manual reconciliation is required for an interrupted action"
                    self.store.append("TaskRecoveryRequired", {"actions": [node.action.action_id for node in unsafe]}, task_id=session.task_id)
                    self._persist(session)
                elif session.state in {TaskState.RUNNING, TaskState.VERIFYING, TaskState.RECOVERING, TaskState.REPLANNING, TaskState.WAITING_FOR_RESOURCE, TaskState.READY} or (session.state == TaskState.WAITING_FOR_APPROVAL and not self._has_undecided_approvals(session)):
                    for node in graph.nodes.values():
                        if node.state == StepState.WAITING_FOR_RESOURCE:
                            node.state = StepState.PENDING
                    session.state = TaskState.PAUSED
                    session.error = "task was interrupted; resume explicitly"
                    self.store.append("TaskRecoveryRequired", {"reason": session.error}, task_id=session.task_id)
                    self._persist(session)
                self.sessions[session.task_id] = session
                restored.append(session.task_id)
            except Exception as exc:
                self.store.append("TaskRestoreFailed", {"error": f"{type(exc).__name__}: {exc}"}, task_id=record["task_id"])
        return restored

    @staticmethod
    def _action_from_snapshot(value: dict[str, Any]):
        from systemai.contracts.models import ActionIntent

        return ActionIntent.model_validate(value)

    def reconcile_unresolved_actions(self) -> list[dict[str, Any]]:
        """Mark unresolved dispatched actions unknown; caller must inspect external state before retry."""
        unresolved = self.journal.unresolved()
        for item in unresolved:
            if item["status"] in {ActionJournalStatus.DISPATCHING.value, ActionJournalStatus.DISPATCHED.value}:
                with self.store.connect() as c:
                    c.execute("UPDATE action_journal SET status=? WHERE action_id=?", (ActionJournalStatus.COMMIT_STATUS_UNKNOWN.value, item["action_id"]))
                self.store.append("CommitStatusUnknown", {"previous_status": item["status"]}, task_id=item["task_id"], node_id=item["node_id"], action_id=item["action_id"])
        return self.journal.unresolved()

    def _persist(self, session: TaskSession) -> None:
        snapshot = session.snapshot()
        self.store.upsert_task(session.task_id, session.contract.goal_id, session.contract.objective, session.state.value, snapshot)
        for node in session.graph.nodes.values():
            self.store.upsert_node(session.task_id, node.node_id, node.state.value, {"title": node.title, "action": node.action.model_dump(mode="json"), "dependencies": sorted(node.dependencies), "resources": sorted(node.resource_requirements), "attempts": node.attempts, "last_error": node.last_error})
        self.store.replace_edges(session.task_id, session.graph.edges())

    def _has_undecided_approvals(self, session: TaskSession) -> bool:
        return any(
            not (record := self.security_kernel.approvals.get(approval_id)) or record["approved"] is None
            for approval_id in session.pending_approvals.values()
        )

    def _forget_browser_values(self, session: TaskSession) -> None:
        if self.browser:
            for node in session.graph.nodes.values():
                if node.action.capability == "browser.fill":
                    self.browser.forget_value(str(node.action.parameters.get("value_ref", "")))
        for node in session.graph.nodes.values():
            if node.action.capability == "ui.set_value":
                executor = self.gateway.resolve(node.action.capability)
                if hasattr(executor, "forget_value"):
                    executor.forget_value(str(node.action.parameters.get("value_ref", "")))

    @staticmethod
    def _redacted_facts(facts: dict[str, Any]) -> dict[str, Any]:
        # Logs and health bodies may contain secrets; keep them out of events, snapshots, and the API.
        out = dict(facts)
        if "logs" in out:
            out["logs"] = [{"path": x.get("path"), "size": x.get("size")} for x in out.get("logs", [])]
        if isinstance(out.get("health"), dict):
            out["health"] = {key: value for key, value in out["health"].items() if key != "body"}
        return out
