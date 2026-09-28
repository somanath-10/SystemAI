# SystemAI
**Version:** 1.0.0  
**Release scope:** Trusted Core + Developer Diagnosis vertical slice  
**Primary platform target:** macOS first, with platform-neutral core contracts  
**Default operating mode:** local-first, policy-controlled, independently verified

SystemAI is a local-first operating-intelligence layer. A user gives a goal; SystemAI observes the relevant system state, creates a constrained task graph, proposes typed actions, obtains canonical authorization from a trusted security boundary, executes through replaceable capability adapters, verifies the resulting state independently, records durable events, and recovers safely when something fails.

SystemAI deliberately starts with the first product wedge from the production blueprint:

> **Find why this project is not running and fix it.**

It is not an unrestricted desktop bot and it does not give an LLM a root/admin shell.

## What is complete

- Versioned Pydantic contracts: GoalContract, ActionIntent, Observation, VerificationResult, CapabilityDefinition, ResourceScope and provenance metadata.
- One-planner architecture for the developer workflow.
- Validated Task DAG with dependencies, resource requirements and bounded retries.
- SQLite/WAL append-only event store with a hash-chained audit history.
- Crash-safe write-ahead action journal: PREPARED -> AUTHORIZED -> DISPATCHING -> DISPATCHED -> EFFECT_OBSERVED -> VERIFIED.
- `COMMIT_STATUS_UNKNOWN` reconciliation state for crash-after-side-effect scenarios.
- ResourceLeaseManager with deterministic lock ordering, TTLs and fencing tokens.
- Canonical security decisions outside the planner.
- Provenance/taint-aware approval policy.
- Ed25519 signed, action-bound, executor-bound, device-bound, short-lived, single-use capability tokens.
- Approval records rendered from canonical typed actions.
- Bounded filesystem executor with backup/quarantine semantics.
- Process inspection/start/terminate executor with PID-reuse protection.
- Git, environment-shape, package, logs, ports, network, service, container and database-health diagnostics.
- HTTP health executor.
- Sandboxed/argv-only coding command boundary that fails closed when a requested isolation profile cannot be enforced.
- Independent deterministic verifier.
- End-to-end developer-diagnosis planner and repair flow.
- Pause / stop / take-control task states and API controls.
- 50-case initial evaluation catalog and security categories.
- React/Tauri Command Center source.
- Production Rust Security Kernel crate source plus a strict Python reference kernel used by local tests in environments without Rust.
- Existing Cua/macOS V0.2 adapter code retained for V2 integration.

## Later releases
The release model for this repository intentionally breaks the broader product vision into testable versions. The following are later releases: real production macOS desktop automation through the new security kernel, production browser/CDP workflows, local VLM/OCR perception, model-cost routing, qualified skill compilation, monitoring/automations, voice, Windows/Linux production implementations and multi-device execution.

The full product-level completion criteria from the master blueprint remain preserved in `docs/source/SystemAI_MASTER_BLUEPRINT_UPDATED.md`.

## Authority invariant

Every consequential action must fit this chain:

```text
User / Trusted Event
  -> GoalContract
  -> Validated Task DAG
  -> Resource Lease
  -> Typed ActionIntent
  -> Provenance
  -> Security Kernel
  -> Canonical Risk / Policy
  -> Approval when required
  -> Signed Capability
  -> Trusted Executor
  -> Real System
  -> Fresh Observation
  -> Independent Verification
  -> Event Log / Audit
  -> Complete or Recover
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

systemai doctor
systemai diagnose /path/to/project
```

The project can optionally include `.systemai/project.json`:

```json
{
  "name": "my-app",
  "runtime": "python",
  "start": ["python", "app.py"],
  "test": ["pytest", "-q"],
  "cwd": ".",
  "expected_port": 8000,
  "health_url": "http://127.0.0.1:8000/health",
  "required_env": ["DATABASE_URL"],
  "log_files": ["app.log"]
}
```

Project-provided executable instructions are treated as untrusted provenance. SystemAI therefore pauses for a canonical approval before running declared project commands or terminating conflicting processes.

## Local API

```bash
systemai-api
```

Default development API: `127.0.0.1:8765`.

Important: HTTP is a development/debug interface in source. The production architecture uses authenticated local IPC (Unix-domain socket on macOS/Linux, named pipe on Windows).

## Tests

```bash
make test
```

The suite includes the original V0.x core tests plus tests for capability signing/replay, canonical risk, provenance approvals, event-chain integrity, resource leases, action journaling, sandbox behavior, diagnosis safety and a real local port-conflict repair workflow.

## Documentation map

Start with:

1. `docs/MASTER_INDEX.md`
2. `docs/guides/COMPLETE_GUIDE.md`
3. `docs/architecture/ARCHITECTURE.md`
4. `docs/security/SECURITY_MODEL.md`
5. `docs/guides/DEVELOPMENT_GUIDE.md`
6. `docs/reference/CONTRACTS_AND_API.md`
7. `docs/research/OPEN_SOURCE_REFERENCE_MATRIX.md`
8. `docs/roadmap/VERSIONING_AND_ROADMAP.md`
9. `docs/source/SystemAI_MASTER_BLUEPRINT_UPDATED.md`

## Repository layout

```text
apps/desktop/                React + Tauri Command Center source
src/systemai/                Python orchestrator/reference runtime
native/security-kernel/      Rust production security-kernel crate source
native/privileged-helper/    Later narrow elevated helper contract
contracts/                   Cross-language schema export location
storage/                     Runtime data/migrations documentation
sandbox/                     Isolation profiles/runtime documentation
evals/                       SystemAI evaluation catalog
config/                      Policy/capability/model configuration
scripts/                     Development, demo, acceptance and audit helpers
docs/                        Complete architecture and guides
tests/                       Unit/integration/adversarial tests
```

## Core engineering rule

If a new feature cannot pass through typed authority, scope, policy, signed capability, trusted execution and independent verification, it does not receive consequential host authority.
