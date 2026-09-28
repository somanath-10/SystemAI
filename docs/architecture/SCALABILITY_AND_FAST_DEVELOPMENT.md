# Scalability and Fast Development Architecture

## Goal

SystemAI must be easy to extend without weakening the authority boundary. Fast development comes from stable contracts and replaceable adapters, not from allowing features to bypass policy.

## Stable-core / replaceable-edge model

The following contracts are intentionally stable:

1. `GoalContract`
2. `TaskNode` / `TaskGraph`
3. `ActionIntent`
4. `CapabilityDefinition`
5. `Observation`
6. `VerificationResult`
7. signed capability claims
8. append-only event schema

Everything that touches the outside world is replaceable behind an adapter:

- planner/model provider
- desktop driver
- browser driver
- API/MCP connector
- filesystem/process/service/network executor
- sandbox runtime
- verifier
- diagnosis probe
- memory retriever

This lets teams develop modules in parallel and test them with mock backends.

## Why V1 uses SQLite

V1 uses SQLite in WAL mode because a single-device local agent benefits from low operational overhead, transactional consistency, easy backup, and fast iteration. The event log is the durable truth; projections can later move to PostgreSQL or specialized stores without changing agent contracts.

Scale-out trigger examples:

- concurrent remote devices or many users -> PostgreSQL
- high-volume semantic memory -> Qdrant or another dedicated vector store
- distributed event processing -> NATS/Kafka only after measured need
- high availability -> external database + replicated services

Do not introduce distributed infrastructure merely because the long-term product may need it.

## Module development rule

A new capability is accepted only when it has:

1. a typed capability definition;
2. a canonical risk/reversibility classification;
3. a bounded resource-scope model;
4. a trusted executor implementation;
5. at least one independent verifier;
6. unit and integration tests;
7. failure/recovery behavior;
8. audit/event output;
9. documentation and examples.

## Fast local test loop

```bash
make compile
make test
python scripts/run_v1_acceptance.py
```

Use the mock executor for orchestration tests. Use a real backend only in platform integration suites.

## Parallel team ownership

Suggested ownership boundaries:

- Core/orchestration: DAG, scheduler, event store, leases
- Security: Rust kernel, policies, capabilities, approvals, provenance, secrets
- Developer tools: files/Git/process/port/log/env/package diagnosis
- Desktop: Cua/native adapters and platform tests
- Browser: Playwright/CDP/profile/skills
- Perception: accessibility normalization, OCR/CV/VLM
- Evaluation: resettable tasks, metrics, adversarial tests
- UI: Tauri/React Command Center

Changes across boundaries are made through versioned contracts rather than direct internal imports.

## Performance principles

- event-driven monitoring; no polling LLM loops
- structured APIs/accessibility before screenshots
- retrieve only relevant context
- deterministic verification before semantic verification
- bounded concurrency through resource leases
- SQLite transactions and prepared statements for local state
- short-lived observations; do not persist huge screenshots by default
- batch low-risk diagnostics where safe
- cache immutable metadata and invalidate on observable state change

## Release discipline

Every release contains:

- schema versions
- migration scripts when persistence changes
- changelog
- acceptance report
- dependency inventory
- security limitations
- reproducible test commands

Breaking contract changes require a major contract-version bump even if the product version remains within the same release family.
