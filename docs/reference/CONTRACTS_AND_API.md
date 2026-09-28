# Contracts and API Reference

## Core contracts

### GoalContract

Fields:

- `goal_id`
- `objective`
- `constraints[]`
- `success_conditions[]`
- `forbidden_effects[]`
- `expected_artifacts[]`
- `resource_scope[]`
- `approval_policy`
- `priority`
- `privacy_profile`
- `budget_profile`
- `actor_id`
- `session_id`

The goal contract is the stable boundary the planner is not allowed to silently redefine.

### ActionIntent

Important fields:

- `action_id`, `task_id`, `node_id`
- namespaced `capability`
- semantic `target`
- typed/structured `parameters`
- `expected_result`
- `verification[]`
- `expected_effects[]`
- `forbidden_effects[]`
- `resource_scope[]`
- planner `risk_hint`
- planner `expected_reversibility`
- `requires_elevation`, `requires_confirmation`
- `idempotency_key`
- `provenance[]`

Planner risk/reversibility values are advisory.

### ActionResult

Distinguishes:

- action status;
- effect status: confirmed / unverifiable / suspected no-op / failed;
- executor;
- output;
- warnings/fallback;
- side effects;
- timing/error.

A completed ActionResult does not bypass verification.

### Observation

Carries source, freshness/generation, trust, sensitivity, hash, structured data, artifact reference, redactions and provenance.

### CapabilityDefinition

first release metadata includes:

- canonical base risk;
- executor;
- reversibility;
- idempotence/retry safety;
- compensation strategy;
- required permissions;
- supported verifiers;
- scope model.

### ResourceLease

Includes resource, holder task/node, lease ID, fencing token and expiry.

### CapabilityTokenClaims

Ed25519-signed claims bind exact action/executor/device/session/scope/parameters/approval/nonce.

## first release capabilities

### Files

- `file.read`
- `file.write`
- `file.move`
- `file.delete` (quarantine/trash semantics only)
- `directory.list`
- `directory.create`

### Developer/system observations

- `git.inspect`
- `environment.inspect`
- `package.inspect`
- `log.inspect`
- `process.list`
- `process.inspect`
- `port.inspect`
- `network.inspect`
- `service.inspect`
- `container.inspect`
- `database.inspect`
- `http.health`

### Bounded mutations

- `process.start`
- `process.terminate`
- `sandbox.run`
- `test.run`

Desktop/browser capabilities from V0.2 remain registered for forward compatibility but are not part of first release's production acceptance gate.

## Local development HTTP API

### `GET /health`

Returns first release version and event-chain integrity.

### `GET /capabilities`

Returns capability metadata.

### `POST /tasks/developer-diagnosis`

Body:

```json
{
  "project_root": "/absolute/path",
  "goal": "Find why this project is not running and fix it.",
  "autonomy_mode": "standard_auto"
}
```

### `POST /tasks/{task_id}/approval`

```json
{
  "action_id": "act_...",
  "approved": true,
  "reason": "Reviewed exact canonical action"
}
```

### Control endpoints

- `/pause`
- `/take-control`
- `/cancel`

### Approval/event inspection

- `GET /approvals/{approval_id}`
- `GET /events?task_id=...`

## Production IPC note

This HTTP interface is for first release development and Command Center prototyping. Final privileged communication is expected to use authenticated Unix sockets on macOS/Linux and Windows named pipes on Windows.
