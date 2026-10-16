from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
import hashlib
import json
from dataclasses import asdict
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
from systemai.cost import CostBudget, CostController
from systemai.core.task_graph import TaskGraph, TaskNode
from systemai.desktop import DesktopControlService
from systemai.execution.browser import PlaywrightExecutor, file_sha256
from systemai.intelligence import LocalFirstModelRouter, RoutingDecision, RoutingRequest
from systemai.intelligence.confidence import evidence_confidence
from systemai.intelligence.ollama import OllamaClient
from systemai.intelligence.openai_responses import OpenAIResponsesClient
from systemai.intelligence.openai_speech import OpenAISpeechClient
from systemai.intelligence.openai_tools import OpenAIToolsClient
from systemai.monitoring import ProcessMonitor
from systemai.security.origin import browser_origin
from systemai.execution.base import ExecutionGateway
from systemai.orchestration.action_journal import ActionJournal
from systemai.orchestration.event_store import EventStore
from systemai.orchestration.leases import ResourceBusy, ResourceLeaseManager
from systemai.planner.developer import DeveloperDiagnosisPlanner
from systemai.security.kernel import SecurityContext, SecurityKernel
from systemai.skills.registry import preview_candidate
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
    parent_task_id: str | None = None
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
            "parent_task_id": self.parent_task_id,
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
                    "confidence": evidence_confidence(n.action, self.verifications.get(n.action.action_id)),
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
        cost: CostController | None = None,
        process_monitor: ProcessMonitor | None = None,
        local_models: OllamaClient | None = None,
        openai: OpenAIResponsesClient | None = None,
        speech: OpenAISpeechClient | None = None,
        openai_tools: OpenAIToolsClient | None = None,
        cloud_budget: CostBudget | None = None,
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
        self.cost = cost or CostController(store=store)
        self.model_router = LocalFirstModelRouter(self.cost)
        self.process_monitor = process_monitor
        self.local_models = local_models
        self.openai = openai
        self.speech = speech
        self.openai_tools = openai_tools
        self.cloud_budget = cloud_budget or CostBudget(max_external_cost_usd=0, max_external_calls=0,
                                                       max_external_vision_calls=0)
        self._monitor_task: asyncio.Task | None = None
        self.autonomy_mode = autonomy_mode
        self.sessions: dict[str, TaskSession] = {}

    async def create_developer_task(
        self,
        goal: str,
        project_root: Path,
        *,
        actor_id: str = "local-user",
        autonomy_mode: str | None = None,
        parent_task_id: str | None = None,
    ) -> TaskSession:
        self._validate_parent(parent_task_id)
        project_root = Path(project_root).expanduser().resolve(strict=True)
        autonomy_mode = autonomy_mode or self.autonomy_mode
        if autonomy_mode not in {"observe", "assist", "standard_auto"}:
            raise ValueError(f"unsupported autonomy mode: {autonomy_mode}")
        task_id = f"task_{uuid4().hex[:16]}"
        contract = self.planner.goal_contract(goal, project_root, actor_id=actor_id)
        self._set_cost_budget(task_id, contract, new=True)
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
            parent_task_id=parent_task_id,
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

    async def route_inference(self, request: RoutingRequest) -> RoutingDecision:
        if request.task_id not in self.sessions:
            raise KeyError(request.task_id)
        status = await self.local_model_status()
        models = status["models"]
        available_request = request.model_copy(update={
            "task_id": self.cost_task_id(request.task_id),
            "local_small_available": models.get("local_small", False),
            "local_llm_available": models.get("local_llm", False),
            "local_vlm_available": models.get("local_vlm", False),
            "external_available": bool(self.openai and self.openai.configured and request.modality.value != "audio"),
            "specialist_api_available": False,
        })
        decision = self.model_router.route(available_request)
        self.store.append(
            "InferenceRouted",
            {"tier": decision.tier.value, "external": decision.external, "reason": decision.reason},
            task_id=request.task_id,
        )
        return decision

    def cost_summary(self, task_id: str) -> dict[str, Any]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        cost_id = self.cost_task_id(task_id)
        return {
            "cost_task_id": cost_id,
            "budget": self.cost.budget_for(cost_id).model_dump(mode="json"),
            "totals": asdict(self.cost.totals_for(cost_id)),
            "records": [record.model_dump(mode="json") for record in self.cost.records_for(cost_id)],
        }

    def _validate_parent(self, task_id: str | None) -> None:
        if task_id is not None and task_id not in self.sessions:
            raise ValueError("parent task does not exist")

    def cost_task_id(self, task_id: str) -> str:
        seen = set()
        while True:
            if task_id in seen or task_id not in self.sessions:
                raise ValueError("task cost context is missing or cyclic")
            seen.add(task_id)
            parent = self.sessions[task_id].parent_task_id
            if parent is None:
                return task_id
            task_id = parent

    async def local_model_status(self) -> dict[str, Any]:
        status = await self.local_models.status() if self.local_models else {"connected": False, "models": {}}
        status["openai"] = self.openai.status() if self.openai else {"configured": False, "model": None}
        status["speech"] = self.speech.status() if self.speech else {"stt": False, "tts": False}
        status["tools"] = self.openai_tools.status() if self.openai_tools else {"web_search": False, "image_generation": False}
        return status

    def create_assistant_session(self) -> TaskSession:
        task_id = f"task_{uuid4().hex[:16]}"
        contract = GoalContract(objective="Voice assistant conversation")
        self._set_cost_budget(task_id, contract, new=True)
        session = TaskSession(task_id=task_id, contract=contract, project_root=self.data_dir or Path.cwd(),
                              graph=TaskGraph(task_id), diagnosis={"summary": "Assistant session"}, state=TaskState.COMPLETED)
        self.sessions[task_id] = session
        self.store.append("AssistantSessionCreated", {}, task_id=task_id)
        self._persist(session)
        return session

    async def generate_local(self, task_id: str, prompt: str, *, vision_image: bytes | None = None,
                             small: bool = False, model_override: str | None = None) -> dict[str, Any]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        if self.local_models is None:
            raise RuntimeError("local models are not configured")
        kind = "local_vlm" if vision_image is not None else "local_small" if small else "local_llm"
        result = await self.local_models.generate(task_id=self.cost_task_id(task_id), prompt=prompt, kind=kind, cost=self.cost,
                                                  image=vision_image, model_override=model_override)
        self.store.append("LocalInferenceCompleted", {"model": result.model, "kind": kind, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}, task_id=task_id)
        return result.model_dump(mode="json")

    async def generate_openai(self, task_id: str, prompt: str, *, vision_image: bytes | None = None) -> dict[str, Any]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        if self.openai is None:
            raise RuntimeError("OpenAI is not configured")
        result = await self.openai.generate(task_id=self.cost_task_id(task_id), prompt=prompt, image=vision_image, cost=self.cost)
        self.store.append("ExternalInferenceCompleted", {"provider": "openai", "model": result.model,
                                                          "input_tokens": result.input_tokens,
                                                          "output_tokens": result.output_tokens}, task_id=task_id)
        return result.model_dump(mode="json")

    async def add_memory(self, task_id: str, content: str) -> dict[str, str]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        if self.local_models is None:
            raise RuntimeError("local models are not configured")
        embedding = await self.local_models.embed(task_id=self.cost_task_id(task_id), content=content, cost=self.cost)
        note_id = self.store.add_semantic_note(task_id, content, embedding.digest, embedding.vector)
        self.store.append("MemoryNoteCreated", {"note_id": note_id, "model": embedding.model}, task_id=task_id)
        return {"note_id": note_id}

    async def search_memory(self, task_id: str, query: str, limit: int = 5) -> dict[str, Any]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        if self.local_models is None:
            raise RuntimeError("local models are not configured")
        embedding = await self.local_models.embed(task_id=self.cost_task_id(task_id), content=query, cost=self.cost)
        return {"items": self.store.search_semantic_notes(task_id, embedding.digest, embedding.vector, limit)}

    def delete_memory(self, task_id: str, note_id: str) -> None:
        if task_id not in self.sessions or not self.store.delete_semantic_note(task_id, note_id):
            raise KeyError(note_id)
        self.store.append("MemoryNoteDeleted", {"note_id": note_id}, task_id=task_id)

    def skill_candidate(self, task_id: str) -> dict[str, Any]:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        candidate = preview_candidate(self.sessions[task_id].snapshot(), self.security_kernel.registry)
        review = self.store.latest_skill_review(task_id)
        candidate["review"] = review if review and review["candidate_hash"] == candidate["candidate_hash"] else None
        return candidate

    def review_skill_candidate(self, task_id: str, candidate_hash: str, decision: str) -> dict[str, Any]:
        candidate = self.skill_candidate(task_id)
        if candidate_hash != candidate["candidate_hash"]:
            raise ValueError("candidate has changed; fetch the current preview")
        if decision not in {"retain", "reject"}:
            raise ValueError("unsupported review decision")
        if decision == "retain" and candidate["status"] != "reviewable":
            raise ValueError("blocked candidates cannot be retained")
        event = self.store.append(
            "SkillCandidateReviewRecorded",
            {"candidate_hash": candidate_hash, "decision": decision, "non_authorizing": True},
            task_id=task_id,
        )
        candidate["review"] = {**event["payload"], "recorded_at": event["created_at"]}
        return candidate

    async def start_monitoring(self) -> None:
        if self.process_monitor is not None and (self._monitor_task is None or self._monitor_task.done()):
            self._monitor_task = asyncio.create_task(self.process_monitor.run())

    async def stop_monitoring(self) -> None:
        if self.process_monitor is None:
            return
        self.process_monitor.stop()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None

    def monitoring_status(self) -> dict[str, Any]:
        return {"configured": self.process_monitor is not None, "running": bool(self._monitor_task and not self._monitor_task.done())}

    async def create_desktop_observation(self, *, parent_task_id: str | None = None) -> TaskSession:
        self._validate_parent(parent_task_id)
        if self.desktop is None:
            raise RuntimeError("desktop driver is unavailable")
        status = await self.desktop.status()
        if not status.available:
            raise RuntimeError("desktop driver is unavailable")
        task_id = f"task_{uuid4().hex[:16]}"
        contract = GoalContract(objective="Inspect running desktop applications")
        self._set_cost_budget(task_id, contract, new=True)
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
        session = TaskSession(task_id=task_id, contract=contract, project_root=Path.cwd(), graph=graph, diagnosis={"summary": "Desktop observation"}, parent_task_id=parent_task_id)
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
        parent_task_id: str | None = None,
    ) -> TaskSession:
        self._validate_parent(parent_task_id)
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
        self._set_cost_budget(task_id, contract, new=True)
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        self.store.append("PlanCreated", {"nodes": ["desktop-action"]}, task_id=task_id)
        session = TaskSession(task_id=task_id, contract=contract, project_root=self.data_dir or Path.cwd(), graph=graph, diagnosis={"summary": "Desktop action"}, parent_task_id=parent_task_id)
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
        parent_task_id: str | None = None,
    ) -> TaskSession:
        self._validate_parent(parent_task_id)
        if self.browser is None or not self.browser.status()["available"] or self.data_dir is None:
            raise RuntimeError("browser is not configured or Playwright is unavailable")
        self.browser.require_origin(url)
        if expected_url:
            self.browser.require_origin(expected_url)
        if capability not in self.browser.CAPABILITIES:
            raise ValueError("unsupported browser capability")
        if capability not in {"browser.navigate", "browser.observe"} and not (selector or name):
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
            if not upload.is_file() or upload.stat().st_size > 50_000_000:
                raise ValueError("browser upload path must be a file no larger than 50 MB")
            parameters["path"] = str(upload)
            parameters["sha256"] = file_sha256(upload)
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
        self._set_cost_budget(task_id, contract, new=True)
        self.store.append("GoalCreated", contract.model_dump(mode="json"), task_id=task_id)
        self.store.append("PlanCreated", {"nodes": ["browser-action"]}, task_id=task_id)
        session = TaskSession(task_id=task_id, contract=contract, project_root=root, graph=graph, diagnosis={"summary": "Browser action"}, parent_task_id=parent_task_id)
        self.sessions[task_id] = session
        self._persist(session)
        await self.run(task_id)
        return session

    async def run(self, task_id: str) -> TaskSession:
        if getattr(self, "_closed", False):
            raise RuntimeError("Runtime is closed")
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
            if journal_state and journal_state["status"] == ActionJournalStatus.EFFECT_OBSERVED.value:
                result = ActionResult.model_validate(journal_state["result"])
                session.results[action.action_id] = result
                return await self._verify_result(session, node, result)
            if journal_state is None or journal_state.get("status") == ActionJournalStatus.FAILED.value:
                self.journal.prepare(action)
            elif journal_state["status"] == ActionJournalStatus.AUTHORIZED.value:
                # A pre-dispatch restart requires a fresh token, never a stale authorization.
                self.journal.transition(action, ActionJournalStatus.PREPARED, detail={"reason": "reauthorize before dispatch"})
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
            return await self._verify_result(session, node, result)
        finally:
            self.leases.release_many(leases)

    async def _verify_result(self, session: TaskSession, node: TaskNode, result: ActionResult) -> str:
        action = node.action
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
        self._require_controllable(session)
        session.requested_control = TaskState.PAUSED
        session.state = TaskState.PAUSED
        self.store.append("TaskPaused", {}, task_id=task_id)
        self._persist(session)

    def take_control(self, task_id: str) -> None:
        session = self.sessions[task_id]
        self._require_controllable(session)
        self._forget_browser_values(session)
        session.requested_control = TaskState.USER_TAKEOVER
        session.state = TaskState.USER_TAKEOVER
        self.store.append("UserTakeover", {}, task_id=task_id)
        self._persist(session)

    def cancel(self, task_id: str) -> None:
        session = self.sessions[task_id]
        if session.state == TaskState.CANCELLED:
            return
        if session.state != TaskState.USER_TAKEOVER:
            self._require_controllable(session)
        self._forget_browser_values(session)
        session.requested_control = TaskState.CANCELLED
        session.state = TaskState.CANCELLED
        self.store.append("TaskCancelled", {}, task_id=task_id)
        self._persist(session)

    @staticmethod
    def _require_controllable(session: TaskSession) -> None:
        if session.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.USER_TAKEOVER}:
            raise ValueError("task is no longer accepting execution controls")

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
                    parent_task_id=snapshot.get("parent_task_id"),
                    state=TaskState(snapshot["state"]),
                    pending_approvals=dict(snapshot.get("pending_approvals", {})),
                    error=snapshot.get("error"),
                )
                self._set_cost_budget(session.task_id, session.contract)
                for step in snapshot["steps"]:
                    action_id = step["action"]["action_id"]
                    if step.get("result"):
                        session.results[action_id] = ActionResult.model_validate(step["result"])
                    if step.get("verification"):
                        session.verifications[action_id] = VerificationResult.model_validate(step["verification"])
                for node in graph.nodes.values():
                    journal = self.journal.get(node.action.action_id)
                    if journal and journal["status"] == ActionJournalStatus.VERIFIED.value:
                        node.state = StepState.SUCCEEDED
                        if journal.get("result"):
                            session.results[node.action.action_id] = ActionResult.model_validate(journal["result"])
                        with self.store.connect() as c:
                            verified = c.execute("SELECT result_json FROM verification_results WHERE action_id=?", (node.action.action_id,)).fetchone()
                        if verified:
                            session.verifications[node.action.action_id] = VerificationResult.model_validate_json(verified["result_json"])
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
                        journal = self.journal.get(node.action.action_id)
                        if node.state == StepState.WAITING_FOR_RESOURCE or (journal and journal["status"] in {
                            ActionJournalStatus.PREPARED.value, ActionJournalStatus.AUTHORIZED.value,
                            ActionJournalStatus.EFFECT_OBSERVED.value,
                        }):
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

    def close(self) -> None:
        if any(session.lock.locked() for session in self.sessions.values()):
            raise RuntimeError("Cannot close a runtime while a task is executing")
        self._closed = True
        if ownership := getattr(self, "_ownership", None):
            ownership.close()

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

    def _set_cost_budget(self, task_id: str, contract: GoalContract, *, new: bool = False) -> None:
        profile = contract.budget_profile
        default = self.cloud_budget
        if new:
            profile.max_cloud_spend_usd = min(profile.max_cloud_spend_usd or default.max_external_cost_usd,
                                              default.max_external_cost_usd)
            profile.max_cloud_calls = min(profile.max_cloud_calls or default.max_external_calls,
                                          default.max_external_calls)
            profile.max_image_calls = min(profile.max_image_calls or default.max_external_vision_calls,
                                          default.max_external_vision_calls)
            profile.max_audio_seconds = int(min(profile.max_audio_seconds or default.max_external_audio_seconds,
                                                default.max_external_audio_seconds))
        self.cost.set_budget(task_id, CostBudget(
            max_external_cost_usd=min(profile.max_cloud_spend_usd, default.max_external_cost_usd),
            max_external_calls=min(profile.max_cloud_calls, default.max_external_calls),
            max_external_vision_calls=min(profile.max_image_calls, default.max_external_vision_calls),
            max_external_audio_seconds=min(profile.max_audio_seconds, default.max_external_audio_seconds),
            prefer_local=contract.privacy_profile != "cloud-first",
        ))

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
