from __future__ import annotations

from dataclasses import dataclass

from systemai.config import Settings
from systemai.core.capabilities import CapabilityRegistry, default_capabilities
from systemai.core.runtime import SystemAIRuntime
from systemai.desktop import DesktopControlService
from systemai.execution import (
    CuaCLIClient,
    CuaCLIConfig,
    CuaDesktopExecutor,
    ExecutionGateway,
    LocalExecutor,
    PlaywrightExecutor,
)
from systemai.memory import AuditLedger, MemoryStore
from systemai.monitoring import EventBus
from systemai.planner import OpenAIResponsesModel, RuleBasedPlanner, StructuredPlanner
from systemai.recovery import RecoveryEngine
from systemai.security import CapabilityTokenService, PolicyKernel
from systemai.verification import DesktopVerificationProbe, Verifier


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    registry: CapabilityRegistry
    runtime: SystemAIRuntime
    event_bus: EventBus
    audit: AuditLedger
    memory: MemoryStore
    desktop: DesktopControlService | None = None


def build_container(*, planner_mode: str = "rule") -> AppContainer:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    registry = default_capabilities()
    policy = PolicyKernel(registry)

    desktop: DesktopControlService | None = None
    executors = []
    if settings.enable_desktop:
        if settings.desktop_backend != "cua-cli":
            raise ValueError(f"unsupported desktop backend: {settings.desktop_backend}")
        cua_client = CuaCLIClient(
            CuaCLIConfig(
                binary=settings.cua_driver_binary,
                socket_path=settings.cua_driver_socket,
                timeout_seconds=settings.cua_timeout_seconds,
            )
        )
        desktop = DesktopControlService(cua_client, session=settings.desktop_session)
        # Desktop executor is intentionally registered before LocalExecutor so
        # application.launch uses the semantic driver when desktop control is enabled.
        executors.append(CuaDesktopExecutor(cua_client, session=settings.desktop_session))
    executors.append(LocalExecutor())
    gateway = ExecutionGateway(executors)
    if settings.enable_browser:
        gateway.register(PlaywrightExecutor(headless=settings.browser_headless))

    event_bus = EventBus()
    audit = AuditLedger(settings.data_dir / "audit.db")
    memory = MemoryStore(settings.data_dir / "memory.db")

    if planner_mode == "openai":
        model = OpenAIResponsesModel()
        planner = StructuredPlanner(
            model,
            capability_summary=lambda: [c.model_dump(mode="json") for c in registry.list()],
        )
    else:
        planner = RuleBasedPlanner()

    runtime = SystemAIRuntime(
        planner=planner,
        policy=policy,
        gateway=gateway,
        verifier=Verifier(DesktopVerificationProbe(desktop) if desktop else None),
        recovery=RecoveryEngine(),
        memory=memory,
        audit=audit,
        event_bus=event_bus,
        token_service=CapabilityTokenService(),
        allowed_roots=settings.allowed_root_paths,
        allow_elevation=settings.allow_elevation,
    )
    return AppContainer(settings, registry, runtime, event_bus, audit, memory, desktop)
