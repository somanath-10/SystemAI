from __future__ import annotations

from pathlib import Path

from systemai.config import Settings
from systemai.cost import CostBudget, CostController
from systemai.intelligence.ollama import OllamaClient
from systemai.intelligence.openai_responses import OpenAIResponsesClient
from systemai.intelligence.openai_speech import OpenAISpeechClient
from systemai.intelligence.openai_tools import OpenAIToolsClient
from systemai.core.capabilities import default_capabilities
from systemai.desktop import DesktopControlService, DesktopToolClient
from systemai.execution import DiagnosticExecutor, FileSystemExecutor, HttpExecutor, PlaywrightExecutor, ProcessExecutor, SandboxExecutor
from systemai.execution.authorized_browser import AuthorizedBrowserExecutor
from systemai.execution.authorized_cua import AuthorizedCuaExecutor
from systemai.execution.base import ExecutionGateway
from systemai.execution.cua_cli import CuaCLIClient, CuaCLIConfig
from systemai.orchestration import ActionJournal, EventStore, ResourceLeaseManager, SystemAIRuntime
from systemai.monitoring import EventBus, ProcessMonitor
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
    event_bus = EventBus()

    async def persist_monitor_event(event) -> None:
        store.append("MonitorEvent", {"event_type": event.event_type, "source": event.source, "payload": event.payload})
        if event.source == "process_monitor" and event.event_type in {"PROCESS_STARTED", "PROCESS_EXITED"}:
            for rule_id in store.match_monitor_rules(event.event_type, str(event.payload.get("name", ""))):
                store.append("MonitorAlert", {"rule_id": rule_id, "event_type": event.event_type,
                                              "process_name": event.payload["name"], "pid": event.payload.get("pid")})

    event_bus.subscribe("*", persist_monitor_event)
    process_monitor = ProcessMonitor(event_bus, interval_seconds=settings.process_monitor_interval_seconds) if settings.enable_process_monitor else None
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
    openai_provider = OpenAIResponsesClient(
        api_key=settings.openai_api_key.get_secret_value(), model=settings.openai_model,
        input_usd_per_million=settings.openai_input_usd_per_million,
        output_usd_per_million=settings.openai_output_usd_per_million,
        pricing_verified_at=settings.openai_pricing_verified_at,
        max_input_tokens=settings.openai_max_input_tokens, max_output_tokens=settings.openai_max_output_tokens,
        timeout=settings.openai_timeout_seconds, enabled=settings.enable_openai,
    )
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
        cost=CostController(store=store),
        process_monitor=process_monitor,
        local_models=OllamaClient(settings.ollama_url, small=settings.ollama_small_model, text=settings.ollama_text_model,
                                  vision=settings.ollama_vision_model, embedding=settings.ollama_embedding_model,
                                  timeout=settings.ollama_timeout_seconds),
        openai=openai_provider,
        speech=OpenAISpeechClient(openai_provider, enabled=settings.enable_openai_speech,
                                  stt_model=settings.openai_stt_model, tts_model=settings.openai_tts_model,
                                  voice=settings.openai_tts_voice, stt_cost=settings.openai_stt_max_call_cost_usd,
                                  tts_cost=settings.openai_tts_max_call_cost_usd),
        openai_tools=OpenAIToolsClient(openai_provider, search_fee=settings.openai_web_search_usd_per_call,
                                      image_model=settings.openai_image_model,
                                      image_cost=settings.openai_image_max_call_cost_usd, data_dir=data_dir),
        cloud_budget=CostBudget(max_external_cost_usd=settings.openai_max_task_spend_usd,
                                max_external_calls=settings.openai_max_task_calls,
                                max_external_vision_calls=settings.openai_max_task_vision_calls,
                                max_external_audio_seconds=settings.openai_max_task_audio_seconds),
        autonomy_mode=autonomy_mode or settings.autonomy_mode,
    )
    runtime.restore_sessions()
    return runtime
