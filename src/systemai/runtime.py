from __future__ import annotations

from pathlib import Path

from systemai.config import Settings
from systemai.core.capabilities import default_capabilities
from systemai.desktop import DesktopControlService, DesktopToolClient
from systemai.execution import DiagnosticExecutor, FileSystemExecutor, HttpExecutor, PlaywrightExecutor, ProcessExecutor, SandboxExecutor
from systemai.execution.authorized_browser import AuthorizedBrowserExecutor
from systemai.execution.authorized_cua import AuthorizedCuaExecutor
from systemai.execution.base import ExecutionGateway
from systemai.execution.cua_cli import CuaCLIClient, CuaCLIConfig
from systemai.orchestration import ActionJournal, EventStore, ResourceLeaseManager, SystemAIRuntime
from systemai.planner import DeveloperDiagnosisPlanner
from systemai.security import ApprovalStore, CapabilitySigner, CapabilityVerifier, SecurityKernel
from systemai.verification import PostconditionVerifier


VERSION = "1.0.0"


def build_runtime(
    *,
    data_dir: Path,
    autonomy_mode: str | None = None,
    desktop_client: DesktopToolClient | None = None,
    settings: Settings | None = None,
) -> SystemAIRuntime:
    settings = settings or Settings()
    data_dir = Path(data_dir).expanduser().resolve(strict=False)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_dir.chmod(0o700)
    store = EventStore(data_dir / "systemai.sqlite3")
    approvals = ApprovalStore(data_dir / "systemai.sqlite3")
    signer = CapabilitySigner.load_or_create(data_dir / "keys" / "capability-ed25519.pem")
    registry = default_capabilities()
    kernel = SecurityKernel(registry=registry, signer=signer, approvals=approvals)
    gateway = ExecutionGateway()
    if desktop_client is None and settings.enable_desktop:
        desktop_client = CuaCLIClient(CuaCLIConfig(
            binary=settings.cua_driver_binary,
            socket_path=settings.cua_driver_socket,
            timeout_seconds=settings.cua_timeout_seconds,
        ))
    desktop = DesktopControlService(desktop_client, session=settings.desktop_session) if desktop_client else None
    browser = PlaywrightExecutor(
        headless=settings.browser_headless,
        channel=settings.browser_channel,
        profile_dir=(settings.browser_profile_dir or data_dir / "browser-profile").expanduser(),
        download_dir=(settings.browser_download_dir or data_dir / "downloads").expanduser(),
        allowed_origins=settings.browser_origins,
    ) if settings.enable_browser else None
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
    if desktop_client:
        gateway.register(AuthorizedCuaExecutor(
            desktop_client,
            verifier=CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id="computer", device_id="local"),
            event_store=store,
            session=settings.desktop_session,
            artifact_dir=data_dir / "artifacts",
        ))
    if browser:
        gateway.register(AuthorizedBrowserExecutor(
            browser,
            verifier=CapabilityVerifier.from_pem(signer.public_key_pem(), executor_id="browser", device_id="local"),
            event_store=store,
        ))
    runtime = SystemAIRuntime(
        planner=DeveloperDiagnosisPlanner(),
        security_kernel=kernel,
        gateway=gateway,
        verifier=PostconditionVerifier(desktop=desktop, browser=browser),
        desktop=desktop,
        browser=browser,
        data_dir=data_dir,
        allowed_applications=settings.desktop_app_ids,
        store=store,
        journal=ActionJournal(store),
        leases=ResourceLeaseManager(store),
        autonomy_mode=autonomy_mode or settings.autonomy_mode,
    )
    runtime.restore_sessions()
    return runtime
