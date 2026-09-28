import asyncio
from pathlib import Path

import pytest

from systemai.contracts.models import TaskRequest
from systemai.core.capabilities import default_capabilities
from systemai.core.runtime import SystemAIRuntime
from systemai.execution import ExecutionGateway, LocalExecutor
from systemai.memory import AuditLedger, MemoryStore
from systemai.monitoring import EventBus
from systemai.planner import RuleBasedPlanner
from systemai.recovery import RecoveryEngine
from systemai.security import CapabilityTokenService, PolicyKernel
from systemai.verification import Verifier


@pytest.mark.asyncio
async def test_runtime_writes_and_verifies_file(tmp_path: Path):
    runtime = SystemAIRuntime(
        planner=RuleBasedPlanner(),
        policy=PolicyKernel(default_capabilities()),
        gateway=ExecutionGateway([LocalExecutor()]),
        verifier=Verifier(),
        recovery=RecoveryEngine(),
        memory=MemoryStore(tmp_path / "memory.db"),
        audit=AuditLedger(tmp_path / "audit.db"),
        event_bus=EventBus(),
        token_service=CapabilityTokenService(b"x" * 32),
        allowed_roots=[tmp_path],
    )
    target = tmp_path / "hello.txt"
    session = await runtime.create_task(TaskRequest(goal=f"write:{target}::hello SystemAI"))
    for _ in range(100):
        snap = runtime.get_snapshot(session.task_id)
        if snap["state"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.01)
    snap = runtime.get_snapshot(session.task_id)
    assert snap["state"] == "completed"
    assert target.read_text() == "hello SystemAI"
