from __future__ import annotations

from systemai.contracts.models import CapabilityDefinition, RiskLevel


class CapabilityRegistry:
    """Semantic capability catalog exposed to planners and the security kernel."""

    def __init__(self) -> None:
        self._items: dict[str, CapabilityDefinition] = {}

    def register(self, capability: CapabilityDefinition) -> None:
        key = capability.name.lower()
        if key in self._items:
            raise ValueError(f"capability already registered: {key}")
        self._items[key] = capability

    def upsert(self, capability: CapabilityDefinition) -> None:
        self._items[capability.name.lower()] = capability

    def get(self, name: str) -> CapabilityDefinition:
        key = name.lower()
        if key not in self._items:
            raise KeyError(f"unknown capability: {name}")
        return self._items[key]

    def has(self, name: str) -> bool:
        return name.lower() in self._items

    def list(self) -> list[CapabilityDefinition]:
        return sorted(self._items.values(), key=lambda c: c.name)


def c(name: str, description: str, risk: RiskLevel, executor: str, **kwargs) -> CapabilityDefinition:
    return CapabilityDefinition(name=name, description=description, risk=risk, executor=executor, **kwargs)


def default_capabilities() -> CapabilityRegistry:
    r = CapabilityRegistry()
    defs = [
        c("file.read", "Read a local file", RiskLevel.OBSERVE, "filesystem", reversible=True, idempotent=True, retry_safe=True, supported_verifiers=["file.exists", "file.hash"]),
        c("file.write", "Create or update a local file with backup", RiskLevel.MEDIUM, "filesystem", reversible=True, compensation_strategy="restore_backup", supported_verifiers=["file.exists", "file.hash"]),
        c("file.move", "Move/rename a local file", RiskLevel.MEDIUM, "filesystem", reversible=True, compensation_strategy="move_back", supported_verifiers=["file.moved", "file.hash"]),
        c("file.delete", "Move a file to quarantine/trash; permanent delete is not a normal path", RiskLevel.HIGH, "filesystem", reversible=True, compensation_strategy="restore_from_quarantine", dangerous=True, supported_verifiers=["file.absent"]),
        c("directory.list", "List a directory", RiskLevel.OBSERVE, "filesystem", reversible=True, idempotent=True, retry_safe=True),
        c("directory.create", "Create a directory", RiskLevel.LOW, "filesystem", reversible=True, retry_safe=True, compensation_strategy="remove_if_empty"),
        c("git.inspect", "Inspect Git branch/status/diff/log", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("environment.inspect", "Inspect environment/config shape without exposing secret values", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("package.inspect", "Inspect package manifests, locks, and installed dependency state", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("log.inspect", "Read bounded project logs", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("process.list", "List running processes", RiskLevel.OBSERVE, "process", reversible=True, idempotent=True, retry_safe=True),
        c("process.inspect", "Inspect one process", RiskLevel.OBSERVE, "process", reversible=True, idempotent=True, retry_safe=True),
        c("process.start", "Start a declared project process", RiskLevel.MEDIUM, "process", reversible=True, compensation_strategy="terminate_started_process", supported_verifiers=["process.alive", "port.listening", "http.health"]),
        c("process.terminate", "Terminate an explicitly targeted process", RiskLevel.HIGH, "process", reversible=False, dangerous=True, supported_verifiers=["process.absent"]),
        c("port.inspect", "Inspect local listening ports and owning processes", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("network.inspect", "Inspect local network state", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("http.health", "Perform a bounded HTTP health request", RiskLevel.OBSERVE, "http", reversible=True, idempotent=True, retry_safe=True),
        c("service.inspect", "Inspect service status when available", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("container.inspect", "Inspect local container runtime and declared containers", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("database.inspect", "Run read-only database health inspection through a declared adapter", RiskLevel.OBSERVE, "diagnostic", reversible=True, idempotent=True, retry_safe=True),
        c("sandbox.run", "Run an argv command in the configured sandbox profile", RiskLevel.MEDIUM, "sandbox", reversible=False, supported_verifiers=["command.exit_code"]),
        c("test.run", "Run a declared project test command in the sandbox", RiskLevel.MEDIUM, "sandbox", reversible=False, supported_verifiers=["command.exit_code"]),
        # Desktop/browser capabilities stay registered for forward-compatible contracts but are not release blockers.
        c("application.list", "List desktop applications visible to an authorized driver", RiskLevel.OBSERVE, "computer", reversible=True, idempotent=True, retry_safe=True),
        c("application.launch", "Launch an installed application", RiskLevel.LOW, "computer", reversible=True),
        c("window.list", "List windows for an application/process", RiskLevel.OBSERVE, "computer", reversible=True, idempotent=True, retry_safe=True),
        c("window.observe", "Capture exact window accessibility state and screenshot", RiskLevel.OBSERVE, "computer", reversible=True, requires_permissions=["accessibility", "screen_recording"]),
        c("window.activate", "Bring an exact window to foreground when explicitly needed", RiskLevel.MEDIUM, "computer", reversible=True, requires_permissions=["accessibility"]),
        c("browser.navigate", "Navigate browser page", RiskLevel.LOW, "browser", reversible=True),
        c("browser.click", "Click a browser element", RiskLevel.MEDIUM, "browser", reversible=True),
        c("browser.fill", "Fill a browser field", RiskLevel.MEDIUM, "browser", reversible=True),
        c("browser.download", "Download a file", RiskLevel.MEDIUM, "browser", reversible=True),
        c("ui.observe", "Inspect accessible UI state", RiskLevel.OBSERVE, "computer", reversible=True),
        c("ui.click", "Invoke a semantic UI element", RiskLevel.MEDIUM, "computer", reversible=True),
        c("ui.set_value", "Set a value on a freshly observed UI element", RiskLevel.MEDIUM, "computer", reversible=True),
        c("screen.capture", "Capture a visible screen/window", RiskLevel.OBSERVE, "computer", reversible=True, requires_permissions=["screen_recording"]),
        c("external.send_message", "Send an external message", RiskLevel.HIGH, "connector", reversible=False, dangerous=True, supports_idempotency_key=True),
        c("software.install", "Install software", RiskLevel.HIGH, "privileged", reversible=False, dangerous=True),
        c("system.change_setting", "Change a system setting", RiskLevel.HIGH, "privileged", reversible=True, dangerous=True),
    ]
    for item in defs:
        r.register(item)
    return r
