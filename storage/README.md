# Storage

SystemAI uses SQLite in WAL mode. The schema is initialized by `systemai.orchestration.event_store.EventStore` and is intentionally compact.

Durable truth:

- append-only hash-chained events;
- task/node projections;
- action journal;
- verification results;
- resource leases and fencing sequence;
- used capability nonces;
- model-call ledger foundation;
- artifact metadata;
- projection checkpoints.

Runtime databases are not committed to source control (`*.db` is ignored).

Schema migrations become explicit versioned migration files before the first persistence-breaking production release. The event schema and exported Pydantic JSON Schemas provide the runtime contract boundary.
