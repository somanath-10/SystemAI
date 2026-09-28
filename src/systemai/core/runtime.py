from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from systemai.contracts.models import (
    ActionResult,
    StepState,
    SystemEvent,
    TaskRequest,
    TaskState,
    VerificationResult,
    VerificationStatus,
)
from systemai.core.state_machine import TaskStateMachine
from systemai.core.task_graph import TaskGraph, TaskNode
from systemai.execution.base import ExecutionGateway
from systemai.memory import AuditLedger, MemoryStore
from systemai.monitoring import EventBus
from systemai.planner import Planner
from systemai.recovery import RecoveryEngine
from systemai.security import CapabilityTokenService, PolicyContext, PolicyKernel
from systemai.verification import Verifier


@dataclass(slots=True)
class TaskSession:
    task_id: str
    request: TaskRequest
    fsm: TaskStateMachine = field(default_factory=TaskStateMachine)
    graph: TaskGraph | None = None
    results: dict[str, ActionResult] = field(default_factory=dict)
    verifications: dict[str, VerificationResult] = field(default_factory=dict)
    pending_action_id: str | None = None
    approved_action_ids: set[str] = field(default_factory=set)
    error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.request.goal,
            "state": self.fsm.state.value,
            "error": self.error,
            "pending_action_id": self.pending_action_id,
            "steps": []
            if self.graph is None
            else [
                {
                    "node_id": n.node_id,
                    "title": n.title,
                    "state": n.state.value,
                    "attempts": n.attempts,
                    "max_attempts": n.max_attempts,
                    "last_error": n.last_error,
                    "action": n.action.model_dump(mode="json"),
                    "result": self.results.get(n.action.action_id).model_dump(mode="json")
                    if n.action.action_id in self.results
                    else None,
                    "verification": self.verifications.get(n.action.action_id).model_dump(mode="json")
                    if n.action.action_id in self.verifications
                    else None,
                }
                for n in self.graph.nodes.values()
            ],
            "transitions": [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "reason": t.reason,
                    "at": t.at.isoformat(),
                }
                for t in self.fsm.history
            ],
        }


class SystemAIRuntime:
    """Coordinates planning, policy, execution, verification, recovery and memory."""

    def __init__(
        self,
        *,
        planner: Planner,
        policy: PolicyKernel,
        gateway: ExecutionGateway,
        verifier: Verifier,
        recovery: RecoveryEngine,
        memory: MemoryStore,
        audit: AuditLedger,
        event_bus: EventBus,
        token_service: CapabilityTokenService,
        allowed_roots: list,
        allow_elevation: bool = False,
    ) -> None:
        self.planner = planner
        self.policy = policy
        self.gateway = gateway
        self.verifier = verifier
        self.recovery = recovery
        self.memory = memory
        self.audit = audit
        self.event_bus = event_bus
        self.token_service = token_service
        self.allowed_roots = allowed_roots
        self.allow_elevation = allow_elevation
        self.sessions: dict[str, TaskSession] = {}

    async def create_task(self, request: TaskRequest) -> TaskSession:
        task_id = f"task_{uuid4().hex[:16]}"
        session = TaskSession(task_id=task_id, request=request)
        self.sessions[task_id] = session
        self.audit.append("TASK_CREATED", {"goal": request.goal}, task_id=task_id)
        await self.event_bus.publish(SystemEvent(event_type="TASK_CREATED", source="runtime", payload={"task_id": task_id, "goal": request.goal}))

        try:
            session.fsm.transition(TaskState.PLANNING, "planning started")
            plan = await self.planner.plan(task_id, request, context={"allowed_roots": [str(p) for p in self.allowed_roots]})
            session.graph = plan.to_graph()
            session.fsm.transition(TaskState.READY, "validated plan created")
            self.audit.append("PLAN_CREATED", plan.model_dump(mode="json"), task_id=task_id)
            self._persist(session)
        except Exception as exc:
            session.error = f"{type(exc).__name__}: {exc}"
            if session.fsm.state == TaskState.PLANNING:
                session.fsm.transition(TaskState.FAILED, "planning failed")
            self.audit.append("TASK_FAILED", {"phase": "planning", "error": session.error}, task_id=task_id)
            self._persist(session)
            return session

        asyncio.create_task(self.run(task_id))
        return session

    async def run(self, task_id: str) -> TaskSession:
        session = self._get(task_id)
        async with session.lock:
            if session.fsm.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
                return session
            if session.graph is None:
                raise RuntimeError("task has no plan")
            if session.fsm.state == TaskState.READY:
                session.fsm.transition(TaskState.EXECUTING, "execution started")
            elif session.fsm.state == TaskState.WAITING_FOR_APPROVAL:
                return session

            while True:
                ready = session.graph.ready_nodes()
                if not ready:
                    if session.graph.successful():
                        session.fsm.transition(TaskState.COMPLETED, "all steps verified")
                        self.audit.append("TASK_COMPLETED", {}, task_id=task_id)
                        self.memory.add_trajectory(session.request.goal, task_id, True, session.snapshot())
                        await self.event_bus.publish(SystemEvent(event_type="TASK_COMPLETED", source="runtime", payload={"task_id": task_id}))
                    elif session.graph.terminal():
                        session.error = "one or more task steps failed"
                        session.fsm.transition(TaskState.FAILED, session.error)
                        self.audit.append("TASK_FAILED", {"error": session.error}, task_id=task_id)
                        self.memory.add_trajectory(session.request.goal, task_id, False, session.snapshot())
                    self._persist(session)
                    return session

                node = sorted(ready, key=lambda n: n.node_id)[0]
                outcome = await self._run_node(session, node)
                self._persist(session)
                if outcome == "waiting":
                    return session
                if outcome == "failed":
                    for descendant in session.graph.descendants(node.node_id):
                        if session.graph.nodes[descendant].state in {StepState.PENDING, StepState.BLOCKED}:
                            session.graph.nodes[descendant].state = StepState.SKIPPED
                    continue

    async def _run_node(self, session: TaskSession, node: TaskNode) -> str:
        action = node.action
        context = PolicyContext(
            task_id=session.task_id,
            user_id=session.request.user_id,
            autonomous=session.request.autonomous,
            allow_elevation=self.allow_elevation,
            allowed_roots=self.allowed_roots,
            approved_action_ids=session.approved_action_ids,
        )
        decision = self.policy.evaluate(action, context)
        self.audit.append("POLICY_DECISION", decision.model_dump(mode="json"), task_id=session.task_id, action_id=action.action_id)

        if decision.decision == "deny":
            node.state = StepState.FAILED
            node.last_error = decision.reason
            self.audit.append("ACTION_DENIED", {"reason": decision.reason}, task_id=session.task_id, action_id=action.action_id)
            return "failed"

        if decision.decision == "require_approval":
            node.state = StepState.WAITING_FOR_APPROVAL
            session.pending_action_id = action.action_id
            session.fsm.transition(TaskState.WAITING_FOR_APPROVAL, decision.reason)
            self.audit.append("APPROVAL_REQUIRED", {"reason": decision.reason}, task_id=session.task_id, action_id=action.action_id)
            await self.event_bus.publish(SystemEvent(event_type="APPROVAL_REQUIRED", source="runtime", payload={"task_id": session.task_id, "action_id": action.action_id, "reason": decision.reason}))
            return "waiting"

        node.state = StepState.RUNNING
        node.attempts += 1
        self.audit.append("ACTION_STARTED", {"capability": action.capability, "attempt": node.attempts}, task_id=session.task_id, action_id=action.action_id)

        token: str | None = None
        if decision.capability_token_required:
            token = self.token_service.issue(
                task_id=session.task_id,
                action_id=action.action_id,
                capability=action.capability,
                scope={"target": action.target.model_dump(exclude_none=True) if action.target else {}},
            )

        try:
            result = await self.gateway.execute(action, capability_token=token)
        except Exception as exc:
            result = ActionResult(
                action_id=action.action_id,
                status="failed",
                effect="failed",
                executor="gateway",
                error=f"{type(exc).__name__}: {exc}",
            )
        session.results[action.action_id] = result
        self.audit.append("ACTION_RESULT", result.model_dump(mode="json"), task_id=session.task_id, action_id=action.action_id)

        session.fsm.transition(TaskState.VERIFYING, "verifying action postconditions")
        verification = await self.verifier.verify(action, result)
        session.verifications[action.action_id] = verification
        self.audit.append("VERIFICATION_RESULT", verification.model_dump(mode="json"), task_id=session.task_id, action_id=action.action_id)

        if verification.status == VerificationStatus.PASSED:
            node.state = StepState.SUCCEEDED
            session.fsm.transition(TaskState.EXECUTING, "step verified")
            return "succeeded"

        session.fsm.transition(TaskState.RECOVERING, "verification did not pass")
        recovery = self.recovery.decide(
            action=action,
            verification=verification,
            attempts=node.attempts,
            max_attempts=node.max_attempts,
            result=result,
        )
        self.audit.append("RECOVERY_DECISION", asdict(recovery), task_id=session.task_id, action_id=action.action_id)

        if recovery.retry:
            node.state = StepState.PENDING
            node.last_error = verification.summary
            session.fsm.transition(TaskState.EXECUTING, "retrying step")
            return "retry"

        node.state = StepState.FAILED
        node.last_error = f"{verification.summary}; recovery={recovery.strategy}"
        session.fsm.transition(TaskState.EXECUTING, "step failed; continue graph cleanup")
        return "failed"

    async def approve(self, task_id: str, action_id: str, approved: bool, reason: str | None = None) -> TaskSession:
        session = self._get(task_id)
        async with session.lock:
            if session.pending_action_id != action_id:
                raise ValueError("action is not awaiting approval")
            if session.graph is None:
                raise RuntimeError("task has no graph")
            node = next((n for n in session.graph.nodes.values() if n.action.action_id == action_id), None)
            if node is None:
                raise KeyError("action not found")
            self.audit.append("APPROVAL_DECISION", {"approved": approved, "reason": reason}, task_id=task_id, action_id=action_id)
            session.pending_action_id = None
            if not approved:
                node.state = StepState.FAILED
                node.last_error = reason or "user denied action"
                session.fsm.transition(TaskState.FAILED, "required action denied")
                session.error = node.last_error
                self._persist(session)
                return session
            session.approved_action_ids.add(action_id)
            node.state = StepState.PENDING
            session.fsm.transition(TaskState.EXECUTING, "action approved")
            self._persist(session)
        asyncio.create_task(self.run(task_id))
        return session

    def get_snapshot(self, task_id: str) -> dict[str, Any]:
        return self._get(task_id).snapshot()

    def _get(self, task_id: str) -> TaskSession:
        if task_id not in self.sessions:
            raise KeyError(task_id)
        return self.sessions[task_id]

    def _persist(self, session: TaskSession) -> None:
        self.memory.put_task(session.task_id, session.request.goal, session.fsm.state.value, session.snapshot())
