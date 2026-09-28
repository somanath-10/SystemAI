# SystemAI Full Product Architecture

This document is the concise current architecture spanning first release through V5. The unabridged design history and research rationale remain in `docs/source/SystemAI_MASTER_BLUEPRINT_UPDATED.md`.

## Product

SystemAI is a local-first operating-intelligence layer. Users specify outcomes rather than click sequences. SystemAI converts a goal into a constrained DAG, obtains narrowly scoped authority, executes through the strongest structured interface available, observes real effects, verifies independently, recovers from failures, and can later qualify repeatable procedures into signed skills.

## Permanent authority path

```text
User / Trusted Automation
  -> GoalContract
  -> Planner + validated Task DAG
  -> Resource Lease
  -> semantic ActionIntent + provenance
  -> Rust Security Kernel
  -> canonical risk/scope/reversibility
  -> user approval when required
  -> signed short-lived capability
  -> Execution Gateway
  -> API/MCP | Browser | Desktop | OS | Sandbox | Privileged helper
  -> Real System
  -> fresh Observation
  -> independent Verification + bounded collateral check
  -> append-only Event/Audit
  -> Complete | Recover | Replan | Human decision
```

The reasoning model cannot mint authority, lower risk, approve itself, expose secrets, or use a general root shell.

## Cost/intelligence path

```text
Deterministic operation
  -> qualified cached skill
  -> tiny/local classifier/parser
  -> benchmarked local LLM/VLM
  -> inexpensive specialist API
  -> premium frontier reasoner only when justified
```

Idle SystemAI should make zero model calls. Known deterministic tasks should make zero remote calls.

## Structured-control preference

```text
Official API
 -> MCP / connector / integration
 -> native application/OS API
 -> DOM/CDP/Playwright
 -> accessibility
 -> known shortcut
 -> local vision/grounding
 -> raw coordinates only as a fallback
```

## Trust domains

### Command Center

React + TypeScript + Tauri. Shows running tasks, exact canonical approvals, evidence, verification, audit, costs and PAUSE/STOP/TAKE CONTROL.

### Python Orchestrator

Owns goals, planning, DAG scheduling, relevant context, diagnosis, recovery, memory and later model/cost routing. It requests authority; it does not own authority.

### Rust Security Kernel

Owns canonical risk, provenance/taint policy, scope, approvals, capability signing, secret authorization, replay controls and high-integrity security events.

### Execution Gateway

Only typed, authorized side effects. Executor families:

- API/MCP
- browser
- desktop/computer
- filesystem
- process/service/network
- database
- sandbox
- privileged helper

### Sandboxed coding worker

Runs untrusted development work with read-only/workspace-write/network-deny/allowlist/disposable profiles.

### Privileged helper

Very narrow Rust service. Accepts operation identifiers + validated parameters + signed capability only; never prompts or arbitrary shell text.

## GoalContract

Contains objective, constraints, success conditions, forbidden effects, expected artifacts, resource scopes, approval policy, privacy policy and budget. Planner changes cannot silently expand authority.

## Task DAG + scheduling

Every complex workflow has durable nodes/edges, retry/recovery budgets and postconditions. The Resource Lease Manager serializes scarce resources such as desktop focus, keyboard, pointer, app/window, browser profile, files, services, ports and databases.

## Provenance / taint

Every important value can preserve source trust and transformation history. Web/email/PDF/UI/terminal/download/project content is observation data, not authority. Summarizing untrusted text with an LLM does not make it trusted.

## Capabilities

Capabilities define risk, scope model, permissions, idempotency, retry safety, reversibility/compensation and verifier support. Production capability tokens use asymmetric signatures and bind to exact session/task/node/action/executor/device/scope/parameters/approval/provenance/expiry/nonce.

## Crash safety

External actions use a journal:

`PREPARED -> AUTHORIZED -> DISPATCHING -> DISPATCHED -> EFFECT_OBSERVED -> VERIFIED`

Crash after dispatch enters `COMMIT_STATUS_UNKNOWN`; SystemAI observes real state before deciding whether retry is safe. Prefer native idempotency keys.

## Verification

Priority:

1. API/database/state assertion
2. filesystem/process/network assertion
3. DOM/accessibility assertion
4. deterministic image comparison
5. local semantic verifier
6. cloud semantic/human verification

Each action carries expected and forbidden effects. Compare only a bounded collateral scope.

## Recovery

Classify first: stale ref, not found, ambiguity, permission, resource busy, no effect, failed postcondition, timeout, network, page/app drift, sandbox denial, budget exhaustion or unknown commit.

Then: re-observe -> re-resolve -> safe retry -> alternate structured executor -> qualified skill alternative -> local vision -> diagnosis -> partial-DAG replan -> cloud escalation -> human decision.

## Desktop

`ComputerExecutor` is stable and backend-neutral. Initial backend: Cua behind SystemAI policy. Future optional backends: agent-ctrl/Open Computer Use/native implementations. Semantic targets are re-resolved against fresh snapshots. macOS permissions belong to a stable signed application/driver identity.

## Browser

Default to a dedicated SystemAI browser profile with isolated cookies/downloads/extensions and origin-bound secret use. API/MCP or Playwright/CDP first. Successful AI exploration can become a deterministic, regression-tested helper. Repair only the step affected by page drift.

## Perception

DOM/accessibility first. If insufficient: targeted screenshot -> perceptual hash/diff -> OCR/CV -> optional screen parser -> local VLM -> cloud vision. Perception suggests targets; it never grants authority.

## Developer diagnosis

The initial product wedge inspects files, Git, manifests, environment shape, processes, ports, services, containers/databases, logs, dependency state, tests and health endpoints. It builds evidence-backed hypotheses, runs low-risk discriminating tests, applies the smallest permitted repair, restarts/retests and verifies the original goal.

## World state and persistence

Durable append-only event log is the primary truth. Projections provide current task/world/capability/skill/cost views. SQLite + WAL first; scale to PostgreSQL/vector/distributed infrastructure only after measured need.

## Memory

- working: current relevant state
- episodic: past task summaries/outcomes
- semantic: approved stable facts
- procedural: qualified skills/repair procedures

Do not place full history into model context.

## Skills

A successful trajectory is only a candidate. Qualification:

`candidate -> provenance analysis -> generalize -> parameterize -> static capability analysis -> sandbox replay -> regression -> policy/human review -> qualified -> signed`

Untrusted/high-risk provenance cannot silently become unattended automation.

## Monitoring

Events from files, processes, services, ports/network, system resources and apps are handled by rules/qualified skills first. AI is invoked only for unresolved exceptions.

## Secrets

Secret Broker stores credentials in OS-native secure storage and enforces origin/application/usage constraints. Models normally see only references. Secrets cannot be written to logs/model context/clipboard unless explicitly permitted.

## Product releases

- first release: trusted core + developer diagnosis
- V2: production macOS desktop + browser + visual fallback
- V3: cost/local intelligence + skills + monitoring + voice + demonstrations
- V4: Windows/Linux + multi-device
- V5: enterprise/product hardening

## Evaluation

SystemAI uses its own resettable state-based suite plus external benchmark families where useful. Track verified task success, unsafe/unauthorized actions, collateral damage, human interventions, recovery, steps, model calls, cost, latency, skill hit/drift, approval errors and prompt-injection attack success.
