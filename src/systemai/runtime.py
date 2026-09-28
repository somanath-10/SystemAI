from __future__ import annotations

from pathlib import Path

from systemai.core.capabilities import default_capabilities
from systemai.execution import DiagnosticExecutor, FileSystemExecutor, HttpExecutor, ProcessExecutor, SandboxExecutor
from systemai.execution.base import ExecutionGateway
from systemai.orchestration import ActionJournal, EventStore, ResourceLeaseManager, SystemAIRuntime
from systemai.planner import DeveloperDiagnosisPlanner
from systemai.security import ApprovalStore, CapabilitySigner, CapabilityVerifier, SecurityKernel
from systemai.verification import PostconditionVerifier


VERSION = "1.0.0"


def build_runtime(
    *,
    data_dir: Path,
    autonomy_mode: str = "standard_auto",
) -> SystemAIRuntime:
    data_dir = Path(data_dir).expanduser().resolve(strict=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    store = EventStore(data_dir / "systemai.sqlite3")
    approvals = ApprovalStore(data_dir / "systemai.sqlite3")
    signer = CapabilitySigner.load_or_create(data_dir / "keys" / "capability-ed25519.pem")
    registry = default_capabilities()
    kernel = SecurityKernel(registry=registry, signer=signer, approvals=approvals)
    gateway = ExecutionGateway()
    for name, cls in [
        ("filesystem", FileSystemExecutor),
        ("process", ProcessExecutor),
        ("diagnostic", DiagnosticExecutor),
        ("http", HttpExecutor),
        ("sandbox", SandboxExecutor),
    ]:
        verifier = CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id=name, device_id="local")
        if cls is FileSystemExecutor:
            executor = cls(verifier=verifier, event_store=store, quarantine_root=data_dir / "quarantine")
        else:
            executor = cls(verifier=verifier, event_store=store)
        gateway.register(executor)
    runtime = SystemAIRuntime(
        planner=DeveloperDiagnosisPlanner(),
        security_kernel=kernel,
        gateway=gateway,
        verifier=PostconditionVerifier(),
        store=store,
        journal=ActionJournal(store),
        leases=ResourceLeaseManager(store),
        autonomy_mode=autonomy_mode,
    )
    runtime.restore_sessions()
    return runtime
