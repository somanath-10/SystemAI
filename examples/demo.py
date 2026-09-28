from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

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


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="systemai-demo-"))
    runtime = SystemAIRuntime(
        planner=RuleBasedPlanner(),
        policy=PolicyKernel(default_capabilities()),
        gateway=ExecutionGateway([LocalExecutor()]),
        verifier=Verifier(),
        recovery=RecoveryEngine(),
        memory=MemoryStore(root / "memory.db"),
        audit=AuditLedger(root / "audit.db"),
        event_bus=EventBus(),
        token_service=CapabilityTokenService(),
        allowed_roots=[root],
    )
    target = root / "hello.txt"
    session = await runtime.create_task(TaskRequest(goal=f"write:{target}::Hello from SystemAI"))
    while runtime.get_snapshot(session.task_id)["state"] not in {"completed", "failed"}:
        await asyncio.sleep(0.05)
    print(runtime.get_snapshot(session.task_id))
    print("Created:", target, target.read_text())


if __name__ == "__main__":
    asyncio.run(main())
