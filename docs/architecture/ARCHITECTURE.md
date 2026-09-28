# SystemAI first release Architecture

## 1. Purpose

first release implements the first production vertical from the consolidated blueprint: **developer-environment diagnosis and bounded repair**. It uses production-oriented contracts so later desktop/browser/local-model capabilities plug in without weakening the authority boundary.

## 2. Corrected process architecture

The master V3 source contains both the correct authority invariant and a visual diagram whose process order could be misread as placing security authorization before an action exists. first release resolves that with this explicit topology:

```text
USER / EVENT
   |
   v
TAURI COMMAND CENTER
   |
   v
PYTHON ORCHESTRATOR
  - GoalContract
  - one planner
  - Task DAG
  - scheduler
  - resource leases
  - recovery / diagnosis
   |
   | typed ActionIntent proposal
   v
TRUSTED SECURITY KERNEL
  - schema / capability lookup
  - canonical risk
  - provenance / taint
  - scope
  - approval verification
  - signed capability
   |
   v
EXECUTION GATEWAY
  - filesystem
  - process
  - diagnostics
  - HTTP
  - sandbox
  - future browser/desktop/API adapters
   |
   v
REAL SYSTEM
   |
   v
FRESH OBSERVATION
   |
   v
INDEPENDENT VERIFIER
   |
   +--> success -> event log / projections / next DAG node
   |
   +--> failure -> retry / reconcile / recover / replan
```

The kernel may also authenticate sessions/IPC separately, but **authorization of a consequential operation happens after a typed ActionIntent exists**.

## 3. first release modules

### 3.1 Contracts

`src/systemai/contracts/models.py`

Defines:

- GoalContract
- BudgetProfile
- ApprovalPolicy
- ResourceScope
- ActionIntent / ActionResult
- Observation
- SourceProvenance / ProvenanceValue
- CapabilityDefinition
- CapabilityTokenClaims
- VerificationSpec / VerificationResult
- ProjectManifest
- Hypothesis / DiagnosisReport
- task/action/risk/sandbox enums

### 3.2 Planner

`planner/developer.py`

first release intentionally uses one planner. The current implementation combines deterministic project inspection with typed remediation planning. A frontier planner can later implement the same output contracts.

### 3.3 Task DAG

`core/task_graph.py`

- rejects missing dependencies and cycles;
- stores typed actions;
- stores resource requirements;
- supports topological execution;
- bounded per-node attempts;
- descendants are skipped after terminal failures.

### 3.4 Resource Lease Manager

`orchestration/leases.py`

Locks scarce resources before dispatch:

- `filesystem:<scope>`
- `process:<pid>`
- `port:<port>`
- later `desktop.focus`, `desktop.keyboard`, `browser-profile:<id>`, `database:<scope>`.

Features:

- deterministic resource ordering to avoid lock-order deadlocks;
- TTL expiration;
- monotonic fencing tokens;
- persisted leases in SQLite.

### 3.5 Security Kernel

Python reference: `security/kernel.py`  
Production Rust crate source: `native/security-kernel/`

The kernel—not the planner—derives:

- canonical risk;
- canonical reversibility;
- approval requirement;
- isolation requirement;
- allowed scope.

### 3.6 Capability signing

`security/signing.py`

Ed25519 signed capability claims bind:

- key ID;
- audience;
- executor ID;
- device ID;
- session/task/node/action IDs;
- action hash;
- capability name;
- scope;
- parameter hash;
- approval ID;
- provenance constraints;
- issue/expiry time;
- nonce;
- max uses.

Executors have verification keys only and cannot mint authority.

### 3.7 Event Store

`orchestration/event_store.py`

SQLite/WAL is the first release runtime source of truth. Events are append-only and hash chained.

Typical events:

- GoalCreated
- ObservationReceived
- PlanCreated
- ResourceLeaseGranted
- ActionPrepared
- PolicyDecision
- ApprovalRequested / ApprovalGranted
- ActionDispatchStarted / ActionDispatched
- VerificationPassed / VerificationFailed
- RecoveryStarted
- TaskCompleted / TaskFailed

### 3.8 Action Journal

`orchestration/action_journal.py`

Lifecycle:

```text
PREPARED
  -> AUTHORIZED
  -> DISPATCHING
  -> DISPATCHED
  -> EFFECT_OBSERVED
  -> VERIFIED
```

Unexpected shutdown after dispatch is reconciled as `COMMIT_STATUS_UNKNOWN`; SystemAI must inspect external state before retrying.

### 3.9 Execution Gateway

`execution/base.py`

Core depends on the abstract `Executor`, not Cua, Playwright, or OS-specific APIs.

first release executors:

- FileSystemExecutor
- ProcessExecutor
- DiagnosticExecutor
- HttpExecutor
- SandboxExecutor

Earlier Cua/Playwright adapters remain in the repository for later versions.

### 3.10 Independent verification

`verification/postcondition.py`

Hard checks include:

- process absent/alive;
- process started from executor result;
- port listening;
- HTTP status;
- command exit code;
- file existence/absence/hash.

Executor success alone never completes the node.

## 4. first release flagship workflow

```text
Goal
 -> read-only project observation
 -> evidence-backed diagnosis
 -> Task DAG
 -> optional conflicting-process termination
 -> start declared project process
 -> verify process/port
 -> verify health endpoint
 -> optional tests
 -> event/audit completion
```

Project-provided commands are untrusted provenance and therefore require approval before execution.

## 5. Scalability strategy

first release deliberately avoids Kafka, Neo4j, Redis and distributed services. SQLite/WAL plus explicit contracts provide faster development and easier deterministic testing.

Scale-up path:

- database: SQLite -> PostgreSQL only if measured concurrency requires it;
- semantic memory: add sqlite-vec first;
- executor processes: local adapters -> supervised local services;
- device runtime: local -> authenticated remote agent only after single-device reliability;
- event transport: durable local event store remains canonical even if a bus is added.

## 6. Fast-development strategy

- one planner instead of an agent swarm;
- narrow executor interfaces;
- deterministic mocks and evaluation fixtures;
- generated cross-language schemas planned before many services exist;
- external projects wrapped by adapters rather than forked into core;
- feature flags/version boundaries prevent unfinished V2/V3 systems from destabilizing first release.
