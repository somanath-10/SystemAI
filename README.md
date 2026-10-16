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
- V2 browser actions (navigate, observe, click, fill, download, upload) through an isolated Chrome profile, exact origin allowlist, approval for mutations, signed execution, and fresh verification.
- V2 desktop action pipeline (application launch, window observation, click, set value) through a Cua driver when installed and permissioned; fake-driver integration tests cover the signed path.
- V3 local-model inference through a loopback-only Ollama adapter when a model is installed, with persisted token usage and availability-aware routing.
- V3 evidence-based confidence on verification results, cost view in Command Center, and durable process-start/exit alert rules.
- V3 task-scoped semantic notes and retrieval through a local embedding model, with model-digest isolation and explicit deletion.
- V3 non-executable skill-candidate previews from completed task snapshots, with canonical risk, provenance, independent-evidence checks, and hash-bound review labels; reviews cannot replay actions.
- Jarvis holographic workspace with streamed OpenAI function calls, browser/Kokoro voice fallback, optional metered OpenAI STT/TTS, sourced web search, image artifacts and configurable MCP tools.
- Shared conversation/linked-task budgets, interruption-safe task tracking, durable Task Center history, and Workspace tools for notes, alerts, skill review, routing and audit. Message offers local text or OpenAI tools. Optional ElevenLabs and explicitly allowlisted read-only MCP calls are also metered.

## Release status
The first release is complete for its declared developer-diagnosis scope. Browser automation is exercised with installed Chrome; native desktop acceptance requires the signed Cua driver and macOS permissions. Local inference, memory, alerts, non-authorizing skill reviews and the holographic voice/OpenAI/MCP integration are implemented. Cloud adapters have mock integration tests; live calls need credentials and verified rate/budget settings. Qualified skills, authenticated IPC, Rust runtime authority and production packaging remain open. Do not treat this source checkout as a production desktop release.

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

Python 3.11+ is required. Cryptography 50.x wheels support Apple Silicon macOS; Intel macOS requires a source build with the upstream OpenSSL/Rust prerequisites. See the [upstream changelog](https://cryptography.io/en/latest/changelog/) for supported build targets.

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

For the complete holographic UI, install both frontend dependency sets and start the integrated launcher:

```bash
npm --prefix jarvis-main ci
npm --prefix apps/desktop/ui ci
make dev
```

Open `http://127.0.0.1:5802/` and unlock with the owner-only key in `SYSTEMAI_DATA_DIR/keys/local-api-token`, or your private `SYSTEMAI_API_TOKEN`. API clients require `Authorization: Bearer <local-access-key>`; the bridge authenticates before creating sessions. No provider key is sent to the UI. Message opens typed chat; Task Center opens task/approval controls. See [the assistant workflow and setup](docs/guides/ASSISTANT_WORKFLOW.md) and [Jarvis integration guide](jarvis-main/README.md). Server secrets stay private; optional speech/search/image settings are disabled placeholders in `.env.example`.

```bash
systemai-api
```

Default development API: `127.0.0.1:8765`.
Task Center: `http://127.0.0.1:5802/?view=tasks`.

Optional local inference: install and start Ollama, install a model, then set `SYSTEMAI_OLLAMA_TEXT_MODEL` (and optionally small/vision model names) in `.env`. `GET /inference/status` reports actual model availability; `POST /tasks/{task_id}/inference/generate` sends bounded prompts to the local model and records usage. The model's text is never granted host-action authority. `GET /tasks/{task_id}/cost` reports usage. With `SYSTEMAI_ENABLE_PROCESS_MONITOR=true`, `/monitor/rules` can create persistent exact-name process-start/exit alerts with cooldowns; rules do not execute actions.

For local inference, `/inference/status` also lists installed Ollama model names. Pass an installed `model` to `/tasks/{task_id}/inference/generate` or choose one in the AI modal; the configured default remains available. To enable OpenAI text or image analysis, fill the disabled-by-default settings in `.env.example` into your private `.env`, including a key, a Responses-compatible model, token rates verified within 30 days, and nonzero task spend/call limits. Create a new task after enabling cloud inference; existing zero-budget tasks remain zero-budget. `POST /tasks/{task_id}/inference/openai` requires `confirm_external: true` and optionally accepts a PNG/JPEG/WebP image. It uses [Responses](https://developers.openai.com/api/docs/guides/text) with `store: false` and no hosted tools; [input tokens are counted](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api) before a durable budget reservation. Rates are user-supplied estimates, not a billing guarantee. Failed or ambiguous requests hold their reservation and block more cloud calls on that task. No OpenAI key is bundled, and live OpenAI calls cannot be tested without one.

For optional semantic memory, install an embedding model and set `SYSTEMAI_OLLAMA_EMBEDDING_MODEL`. `POST /tasks/{task_id}/memory` explicitly indexes a note, `POST /tasks/{task_id}/memory/search` retrieves similar notes, and `DELETE /tasks/{task_id}/memory/{note_id}` removes one from the active index. Notes remain local in the runtime SQLite database; they are not automatically captured from tasks or promoted into executable instructions. Retrieval uses only notes from the same task and exact model digest. The local HTTP interface is still a development interface, not authenticated production IPC; do not store secrets in notes.

`GET /tasks/{task_id}/skill-candidate` derives a non-executable preview from a task's durable snapshot. It blocks candidates with missing provenance, untrusted/secret sources, higher-risk actions, or weak verification. `POST /tasks/{task_id}/skill-candidate/review` accepts the current `candidate_hash` and a `retain` or `reject` decision; the hash-bound decision is kept in the event log for later inspection and is ignored if the candidate changes. This local review label does not save a reusable skill, qualify or replay a task, sign a skill, or bypass the normal action authority chain.

Important: HTTP is a development/debug interface in source. The production architecture uses authenticated local IPC (Unix-domain socket on macOS/Linux, named pipe on Windows).

## Tests

```bash
make test
make check  # also bridge/Chrome, UI build, Rust and acceptance checks
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
jarvis-main/                 Reused holographic UI, voice/media and OpenAI/MCP bridge
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
