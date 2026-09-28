# Changelog

## 1.0.0 — Trusted Core + Developer Diagnosis

- Reframed release versions around testable vertical slices while preserving the full master blueprint.
- Added GoalContract, provenance, resource scope, budget/approval and expanded action contracts.
- Added SQLite/WAL hash-chained event store.
- Added write-ahead action journal and unknown-commit reconciliation state.
- Added ResourceLeaseManager with TTL/fencing tokens.
- Added Ed25519 action-bound capability signing and replay protection.
- Added provenance-aware SecurityKernel with canonical risk/reversibility.
- Added canonical ApprovalStore.
- Added filesystem/process/diagnostic/HTTP/sandbox executors.
- Added independent PostconditionVerifier.
- Added ProjectInspector and DeveloperDiagnosisEngine.
- Added end-to-end developer diagnosis runtime and API/CLI.
- Added 50-case evaluation catalog.
- Added production Rust Security Kernel crate source.
- Updated Command Center source for diagnosis/approval/task control.
- Added comprehensive architecture, security, guide, research and roadmap documentation.
- Retained V0.2 Cua/macOS adapter source for V2 integration.
