# Contributing

SystemAI changes should preserve the authority and verification invariants.

## Before opening a change

- run `pytest`;
- add/update tests for every capability/policy change;
- add adversarial coverage for security changes;
- update capability metadata and verifiers;
- update documentation/ADR when trust boundaries change;
- do not introduce a raw general shell or model-owned privileged handle.

## Pull request checklist

- [ ] Typed contract updated if needed.
- [ ] Canonical risk/scope considered.
- [ ] Approval behavior tested.
- [ ] Executor only accepts signed authority.
- [ ] Independent verifier exists.
- [ ] Retry/idempotency semantics defined.
- [ ] Provenance/taint behavior defined.
- [ ] Eval catalog/test updated.
- [ ] Docs updated.
- [ ] No secret material in fixtures/logs.
