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

- Production Rust kernel integration over authenticated local IPC.
- Stable signed macOS application/driver identity.
- Accessibility + Screen Recording onboarding.
- Cua `ComputerExecutor` backend under SystemAI policy.
- Finder/TextEdit/Calculator/Chrome/VS Code validation.
- desktop leases + takeover detection.
- dedicated SystemAI browser profile.
- Playwright/CDP session manager.
- downloads/uploads/origin policy/Secret Broker integration.
- deterministic browser helper cache and repair-on-drift.
- targeted screenshots/local CV/visual fallback.

## V3 — Cost Intelligence + Learning + Monitoring

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
