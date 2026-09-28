# ADR-001 — Planner / Security Kernel Process Order

**Status:** Accepted for SystemAI V1

## Context

The production blueprint correctly states the authority invariant as:

`GoalContract -> Task DAG -> ActionIntent -> Security Kernel -> Signed Capability -> Executor`.

One visual V3 process diagram placed the Rust Security Kernel between the UI and the Python orchestrator, which could imply that the kernel authorizes a consequential operation before the planner has produced a typed action.

## Decision

SystemAI V1 uses two separate interactions:

1. **Session/transport trust:** UI and orchestrator communication is authenticated and narrow.
2. **Action authority:** the orchestrator proposes a typed ActionIntent; only then does the Security Kernel calculate canonical risk/scope/approval and issue a signed capability.

```text
UI -> Orchestrator -> ActionIntent -> Security Kernel -> signed capability -> Executor
```

The kernel may expose separate session-authentication services, but it never grants generic authority to the planner.

## Consequences

- The model cannot mint or pre-authorize broad privileges.
- Approval screens can be generated from the kernel's canonical typed action.
- Executors can verify exact action authority offline using the kernel public key.
- A compromised planner remains constrained to capabilities/scopes that the kernel accepts.
