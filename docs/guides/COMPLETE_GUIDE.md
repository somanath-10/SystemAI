# SystemAI Complete Guide

This guide explains the project from original idea through the open-source research, the consolidated V3 production architecture, the V1 release scope, how the code works, how to run it, and how later versions extend it.

## 1. Original idea

SystemAI began as an autonomous system-access AI capable of operating installed/inbuilt applications, files, processes, browsers and system resources from a user's goal rather than a sequence of clicks.

The architecture evolved away from `LLM -> mouse/keyboard/root` toward a layered operating-intelligence system because reliable autonomy requires deterministic control, security boundaries, verification, recovery, memory and cost management.

## 2. Core product definition

SystemAI is:

- local-first;
- model-independent;
- typed-capability based;
- policy controlled;
- independently verified;
- event sourced;
- recovery aware;
- progressively cheaper as workflows become deterministic skills.

It is **not**:

- a single unrestricted LLM process;
- a screenshot-click loop;
- a general root shell;
- a hidden monitoring agent;
- a replacement for OS authentication/security boundaries.

## 3. Research journey

The complete source document under `docs/source/` preserves the detailed research. The most important project influences are summarized in `docs/research/OPEN_SOURCE_REFERENCE_MATRIX.md`.

Key architecture lessons:

- UFO/UFO Galaxy -> explicit DAG/state orchestration and future device capability assignment.
- Cua -> model-independent native computer driver and stable permission identity.
- Agent-S -> separate reasoning/grounding and visual reflection, while rejecting direct model-code execution.
- Open Interpreter/Codex runtime patterns -> sandbox policy separate from approval policy.
- Agent Desktop/Open Computer Use/agent-ctrl -> semantic accessibility, compact snapshots, fresh refs.
- Stagehand/Browser Harness -> deterministic cached browser paths, repair only on drift.
- OpenHands/OpenClaw -> isolated action/runtime execution and trusted gateway.
- OpenAdapt -> record/review/compile/qualify/replay workflow learning.
- AppWorld/OSWorld/BrowserGym/AgentDojo/DoomArena -> state-based and adversarial evaluation.

## 4. Version strategy

See `roadmap/VERSIONING_AND_ROADMAP.md`.

V1 intentionally delivers a complete trusted developer-diagnosis vertical slice before attempting universal desktop automation.

## 5. V1 runtime lifecycle

### 5.1 Receive goal

CLI/API/UI receives a project path and goal.

### 5.2 Create GoalContract

The contract fixes:

- objective;
- constraints;
- success conditions;
- forbidden effects;
- resource scope;
- approval policy;
- privacy/budget profile.

The planner may refine the plan but may not silently rewrite these boundaries.

### 5.3 Observe project

Read-only `ProjectInspector` gathers facts. Environment inspection reveals key names only. Repository content remains observation, not trusted authority.

### 5.4 Diagnose

`DeveloperDiagnosisEngineV1` converts evidence into explicit hypotheses and typed recommended actions.

### 5.5 Build DAG

`DeveloperDiagnosisPlannerV1` creates a validated TaskGraph with dependencies and resource requirements.

### 5.6 Acquire resource leases

Resources such as process IDs, ports and filesystem roots are leased with TTLs/fencing tokens so concurrent work cannot conflict silently.

### 5.7 Prepare action journal

The action is written to the journal before dispatch.

### 5.8 Canonical authorization

The Security Kernel independently computes risk, reversibility, scope and approval.

### 5.9 Approval

When required, runtime pauses. Approval is tied to the exact action ID and canonical kernel summary.

### 5.10 Sign capability

The kernel issues a short-lived Ed25519 capability bound to the exact action, parameters, executor, device, session and nonce.

### 5.11 Execute

The gateway routes to the exact registered executor. The executor verifies the token before acting.

### 5.12 Observe and verify

The verifier checks real postconditions such as PID absence, port listening or HTTP health.

### 5.13 Persist

Events, verification, action state and task projections are stored in SQLite/WAL.

### 5.14 Recover

Only explicitly retry-safe operations may auto-retry. Unknown commit state must be reconciled first.

## 6. Source layout

### `src/systemai/contracts`
Shared Python contracts.

### `src/systemai/core`
Capability registry and validated TaskGraph.

### `src/systemai/security`
Python reference Security Kernel, approval store, signing, provenance and legacy compatibility code.

### `src/systemai/orchestration`
EventStore, ActionJournal, ResourceLeaseManager and V1 runtime.

### `src/systemai/execution`
Execution gateway and capability-specific executors/adapters.

### `src/systemai/diagnostics`
Project inspection and evidence-driven developer diagnosis.

### `src/systemai/planner`
One V1 planner plus retained adapters from earlier experiments.

### `src/systemai/verification`
Independent postcondition verification.

### `native/security-kernel`
Production Rust security-authority source.

### `apps/desktop`
React/Tauri Command Center source.

### `evals`
Fixed evaluation catalog.

## 7. Add a new capability

1. Define/update `CapabilityDefinition` in the registry.
2. Define resource scope semantics.
3. Define canonical risk/reversibility in kernel policy if special handling is needed.
4. Implement an executor supporting the capability.
5. Add independent verifier(s).
6. Add a test case for approval/scope/side effects.
7. Add evaluation catalog entries.
8. Document the capability.

Never expose a raw OS primitive merely because it is convenient for the model.

## 8. Add a new planner

Implement the same output contract:

- GoalContract remains authoritative.
- Planner produces a valid DAG/ActionIntent proposals.
- Risk is only a hint.
- Planner never gets a signing key.
- Planner never bypasses policy.

A frontier-cloud planner can therefore be added without changing executors/security.

## 9. Add an external desktop/browser project

Wrap it behind SystemAI executor contracts.

Do not import its security assumptions into the core. For example Cua may enforce its own manifest, but the SystemAI Security Kernel remains the root authorization layer.

## 10. Performance strategy

- deterministic operations first;
- narrow dynamic tool catalogs;
- one planner in V1;
- local read-only observations where possible;
- no continuous screenshots/model calls;
- direct parsers/APIs before GUI;
- SQLite/WAL until measured scale requires more;
- later cache successful workflows as signed skills.

## 11. Cost strategy

The permanent ladder is:

`deterministic -> qualified skill -> local small intelligence -> local LLM/VLM -> cheap specialist API -> premium frontier reasoner`.

V1 records the interfaces/metrics foundation but does not prematurely optimize planner routing before baseline evaluation exists.

## 12. Privacy strategy

- local by default;
- env values not exposed during shape inspection;
- raw screen recording off by default in later versions;
- secret logging forbidden;
- cloud egress policy controlled;
- model/provider adapters swappable;
- demonstration recording later is local/review-first.

## 13. Production path

Before a consumer/enterprise release:

- compile/integrate the Rust kernel;
- authenticated UDS/named-pipe IPC;
- platform secure-store Secret Broker;
- signed/notarized app and driver;
- secure updater;
- SBOM and dependency/model license inventory;
- real macOS benchmark pass;
- browser/desktop prompt-injection tests;
- crash reconciliation tests;
- penetration/threat review.

## 14. Exact V1 limitation statement

The ZIP is a working V1 for the declared **Trusted Core + Developer Diagnosis** release scope. It is not the final universal autonomous desktop product. Real system-wide GUI/browser/local-model/voice/multi-platform functions are versioned explicitly rather than represented as complete when they have not yet been validated.
