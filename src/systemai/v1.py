from __future__ import annotations

from pathlib import Path

from systemai.core.capabilities import default_capabilities
from systemai.execution import DiagnosticExecutorV1, FileSystemExecutorV1, HttpExecutorV1, ProcessExecutorV1, SandboxExecutorV1
from systemai.execution.base import ExecutionGateway
from systemai.orchestration import ActionJournal, EventStore, ResourceLeaseManager, SystemAIV1Runtime
from systemai.planner import DeveloperDiagnosisPlannerV1
from systemai.security import ApprovalStore, CapabilitySigner, CapabilityVerifier, SecurityKernelV1
from systemai.verification import VerifierV1


VERSION = "1.0.0"


def build_v1_runtime(
    *,
    data_dir: Path,
    autonomy_mode: str = "standard_auto",
) -> SystemAIV1Runtime:
    data_dir = Path(data_dir).expanduser().resolve(strict=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    store = EventStore(data_dir / "systemai-v1.sqlite3")
    approvals = ApprovalStore(data_dir / "systemai-v1.sqlite3")
    signer = CapabilitySigner.load_or_create(data_dir / "keys" / "capability-ed25519.pem")
    registry = default_capabilities()
    kernel = SecurityKernelV1(registry=registry, signer=signer, approvals=approvals)
    gateway = ExecutionGateway()
    for name, cls in [
        ("filesystem", FileSystemExecutorV1),
        ("process", ProcessExecutorV1),
        ("diagnostic", DiagnosticExecutorV1),
        ("http", HttpExecutorV1),
        ("sandbox", SandboxExecutorV1),
    ]:
        verifier = CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id=name, device_id="local")
        if cls is FileSystemExecutorV1:
            executor = cls(verifier=verifier, event_store=store, quarantine_root=data_dir / "quarantine")
        else:
            executor = cls(verifier=verifier, event_store=store)
        gateway.register(executor)
    runtime = SystemAIV1Runtime(
        planner=DeveloperDiagnosisPlannerV1(),
        security_kernel=kernel,
        gateway=gateway,
        verifier=VerifierV1(),
        store=store,
        journal=ActionJournal(store),
        leases=ResourceLeaseManager(store),
        autonomy_mode=autonomy_mode,
    )
    runtime.restore_sessions()
    return runtime
