# Versioning and Roadmap

## Why the product is split into versions

The master blueprint has a broad full-product first release completion gate that includes macOS desktop control, browser control, sandboxing, skills, cost routing, security regression, installer/update hardening and other pieces. For fast, measurable development, this repository decomposes that program into smaller product releases while preserving the broader completion gate in the source blueprint.

## first release — Trusted Core + Developer Diagnosis

**Status in this ZIP:** implemented end-to-end for the declared release scope.

Includes:

- Phase-0 style evaluation catalog and state-based tests.
- Trusted contracts.
- Canonical security boundary and asymmetric capabilities.
- Event-sourced orchestration.
- Action journal and crash reconciliation state.
- Resource leases.
- One planner interface.
- Developer project inspection/diagnosis/repair.
- Safe filesystem/process/network/HTTP/Git/env/package/log tools.
- Sandboxed argv command boundary.
- Independent verification.
- Approval UI/API contract.
- Command Center source.
- Full project documentation.

first release flagship goal:

> Find why this project is not running and fix it.

## V2 — Real macOS Desktop + Browser

In progress: signed desktop observation/launch/click/set-value actions and isolated Playwright browser navigation/observation/click/fill/download/upload are implemented with allowlists, approval gates, durable task records, and fresh postcondition checks. Browser actions have passed an installed-Chrome local fixture and Command Center navigation. Native desktop real-app validation, Rust authority over authenticated IPC, and release packaging remain open.

- Production Rust kernel integration over authenticated local IPC.
- Stable signed macOS application/driver identity.
- Accessibility + Screen Recording onboarding.
- Cua `ComputerExecutor` backend under SystemAI policy (implemented, native acceptance pending).
- Finder/TextEdit/Calculator/Chrome/VS Code validation.
- desktop leases + takeover detection.
- dedicated SystemAI browser profile (implemented).
- Playwright/CDP session manager (implemented for one local profile).
- downloads/uploads/origin policy (implemented); Secret Broker integration remains open.
- deterministic browser helper cache and repair-on-drift.
- targeted screenshots/local CV/visual fallback.

## V3 — Cost Intelligence + Learning + Monitoring

In progress: the active runtime persists model usage and enforces task cloud budgets. A loopback-only Ollama text/vision/embedding adapter with installed-model selection, an opt-in OpenAI Responses text/vision adapter with durable spend reservations, provider-availability-aware routing, evidence-based verification confidence, a compact usage view, explicit task-scoped semantic notes, non-executable skill-candidate previews with hash-bound review labels, and durable process-event alert rules are implemented. Local model calls require a running Ollama installation; OpenAI calls require a user key and verified rate/budget configuration, and have only been tested with mocked responses in this checkout.

The Jarvis holographic UI, OpenAI streamed function loop, turn-based STT/TTS adapters, browser/Kokoro fallback, metered web search/image generation and configurable MCP transports are now implemented with mocked provider tests and real Chrome/UI checks. Live cloud calls, camera/gesture/audio hardware and account connectors need external setup. See the assistant workflow guide for feature coverage and cost/security limits.

Still open: calibrated router benchmarks, skill replay/qualification/signing, demonstration capture/review and scheduled/action automations. Candidate previews are non-executable; semantic notes are explicitly submitted, not automatically learned from task history; process rules currently alert only and never execute host actions.

- evaluation-calibrated ModelRouter.
- local LLM/VLM providers.
- ConfidenceEngine based on evidence, not model self-confidence.
- CostController and cost dashboard.
- local embeddings/semantic retrieval.
- Skill Compiler: candidate -> taint analysis -> replay -> qualification -> signing.
- OpenAdapt-style demonstration recording/review/compile flow.
- event-driven monitoring/automations.
- local STT/TTS and optional cloud voice fallbacks.

## V4 — Windows/Linux + Multi-device

- Windows UIA/Win32/UIPI/UAC integration.
- named-pipe security boundary.
- Windows credential integration and sandbox/elevation behavior.
- Linux AT-SPI/X11/Wayland/XDG/D-Bus/systemd/Secret Service integration.
- platform-specific tests.
- remote device registry, encrypted protocol, DAG placement and device-scoped capabilities.

## V5 — Product/Enterprise Hardening

- signed installers, notarization/Authenticode.
- secure updater.
- SBOM and dependency/model inventory.
- migration/backup/recovery.
- enterprise policies and remote administration.
- security attestation where required.
- large benchmark gates and penetration testing.
- support bundles and privacy/retention controls.

## Permanent invariants across every version

### Authority

`Goal -> DAG -> Lease -> ActionIntent -> Provenance -> Security Kernel -> Canonical Risk -> Approval -> Signed Capability -> Executor -> Observation -> Verification -> Audit -> Complete/Recover`

### Cost

`Deterministic -> Qualified Skill -> Small/Local Intelligence -> Local LLM/VLM -> Cheap Specialist API -> Premium Frontier Reasoner`

### Control preference

`API -> MCP/integration -> native API -> DOM/CDP -> Accessibility -> shortcut -> local vision -> raw coordinates`
