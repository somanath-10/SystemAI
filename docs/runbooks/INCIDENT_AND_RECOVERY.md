# Incident and Recovery Runbook

## Task stuck waiting for approval

- inspect task snapshot;
- retrieve canonical approval record;
- approve/deny the exact action;
- never bypass the approval table by editing task state manually.

## Resource busy

- inspect `resource_leases`;
- wait for TTL or release the owning task through normal control flow;
- do not delete active leases without understanding holder/fencing state.

## Crash after side effect

- run runtime reconciliation;
- action becomes `COMMIT_STATUS_UNKNOWN`;
- inspect external state using an independent verifier;
- mark/continue based on observed effect;
- do not blindly replay.

## Event-chain failure

Treat as an integrity incident. Stop consequential automation, preserve DB/WAL copies and investigate storage modification/corruption.

## Signing-key exposure

V1 development key lives under the configured data directory. If exposed:

- stop executors;
- rotate the key;
- invalidate/restart sessions;
- clear old executor trust/public-key configuration;
- investigate issued token/audit history.

Production Rust kernel must own signing-key lifecycle and rotation.
