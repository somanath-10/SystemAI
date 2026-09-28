# Event Sourcing and Crash Safety

## Why V1 uses an append-only event log

SystemAI has many possible projections: task state, world state, approvals, audit, skill candidates, cost and application state. If each becomes an independent truth store, they will eventually disagree.

V1 therefore makes the durable event log the primary execution history and keeps compact projections for fast access.

## Event integrity

Each event stores:

- sequence;
- event ID/type;
- task/node/action IDs;
- canonical JSON payload;
- timestamp;
- previous hash;
- current event hash.

`EventStore.verify_chain()` detects history modification.

## Action write-ahead journal

External effects are separately journaled:

```text
PREPARED
AUTHORIZED
DISPATCHING
DISPATCHED
EFFECT_OBSERVED
VERIFIED
```

### Crash cases

- before DISPATCHING: safe to resume from authorization/planning;
- during DISPATCHING: mark `COMMIT_STATUS_UNKNOWN`;
- after DISPATCHED but before verification: inspect external state before any retry;
- after VERIFIED: do not replay the action.

## Idempotency

Capabilities declare whether they are idempotent/retry-safe and whether the external system supports idempotency keys.

V1 only automatically retries capabilities explicitly marked retry-safe.

## Reversibility

Reversibility is semantic, not a planner guess:

- file write -> backup first;
- file delete -> quarantine/trash first;
- process terminate -> not reversible;
- process start -> compensating stop is possible;
- future code edits -> Git/checkpoint snapshot;
- future DB mutations -> transaction/compensation.

## Resource fencing

Leases use monotonic fencing tokens. A future distributed executor can reject stale work carrying an older fencing token.
