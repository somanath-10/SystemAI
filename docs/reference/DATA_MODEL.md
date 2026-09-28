# V1 Data Model

SystemAI V1 uses SQLite with WAL mode.

## Durable tables

### `events`

Append-only hash-chained event history.

### `tasks`

Fast task projection/snapshot.

### `task_nodes`

Fast node projection.

### `task_edges`

Current DAG edges.

### `action_journal`

Crash-safety lifecycle for real side effects.

### `verification_results`

Independent postcondition results.

### `approvals`

Canonical approval records.

### `resource_leases`

Current leases/holders/fencing tokens/expiry.

### `lease_sequence`

Monotonic fencing-token counter.

### `used_capability_nonces`

Durable replay protection.

### `model_calls`

Reserved V1 schema for measured model/provider usage. Cost routing is a later release.

### `artifacts`

Metadata for larger produced/redacted artifacts.

### `projection_checkpoints`

Projection rebuild/checkpoint state.

## Why SQLite first

- transactional;
- WAL supports local concurrent readers;
- easy backups and deterministic test fixtures;
- no operational dependency;
- fast development;
- enough for a single-machine V1.

Only move to PostgreSQL/event brokers/graph DBs when measured concurrency/scale requires it.

## Secret data

Secret values must not be stored as normal SQLite records. The future Secret Broker uses platform secure storage. V1 environment inspection stores only key names/missing-key facts.
