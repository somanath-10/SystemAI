# SystemAI Documentation Index

This repository contains both the **current first release implementation documentation** and the complete historical/master architecture source that led to it.

## Current implementation documents

- `architecture/ARCHITECTURE.md` — current deployable architecture and trust boundaries.
- `architecture/FULL_PRODUCT_ARCHITECTURE.md` — concise current first release–V5 target architecture.
- `architecture/ADR-001_SECURITY_KERNEL_ORDER.md` — resolves planner/kernel process-order ambiguity from the source blueprint.
- `architecture/EVENT_SOURCING_AND_CRASH_SAFETY.md` — event log, projections, action journal, idempotency and reconciliation.
- `architecture/SCALABILITY_AND_FAST_DEVELOPMENT.md` — module boundaries, scale-out triggers and fast extension rules.
- `security/SECURITY_MODEL.md` — canonical authority, provenance, approvals, capability tokens, scope and secrets.
- `security/THREAT_MODEL.md` — threats and expected mitigations.
- `guides/COMPLETE_GUIDE.md` — end-to-end project guide.
- `guides/DEVELOPMENT_GUIDE.md` — local development and extension workflow.
- `guides/EXTENDING_SYSTEMAI.md` — capability/executor/diagnostic extension guide.
- `guides/BUILD_AND_RUN.md` — install/run/API/UI steps.
- `guides/DEVELOPER_DIAGNOSIS.md` — flagship first release use case.
- `guides/TESTING_AND_EVALUATION.md` — tests, 50-case evaluation catalog and metrics.
- `reference/CONTRACTS_AND_API.md` — data contracts, capabilities, API and CLI.
- `reference/DATA_MODEL.md` — SQLite/WAL persistence model.
- `reference/DEPENDENCY_AND_LICENSE_INVENTORY.md` — direct dependencies, license policy and external-reference rules.
- `research/OPEN_SOURCE_REFERENCE_MATRIX.md` — every major reference project discussed and what SystemAI adopts/rejects.
- `roadmap/VERSIONING_AND_ROADMAP.md` — release versions first release-V5 and relation to the master product roadmap.
- `LIMITATIONS.md` — exact limits of this first release build.

## Master source document

`source/SystemAI_MASTER_BLUEPRINT_UPDATED.md` is the complete updated architecture source. It preserves sections 1-34 and the later V3 production architecture section. When the current implementation docs differ from earlier historical sections, the V3 precedence rules and explicit first release ADRs govern the code in this repository.

## Root project documents

- `README.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `NOTICE.md`
- `VERSION`
