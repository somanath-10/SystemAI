# SystemAI Threat Model

## Assets

- user files/projects;
- credentials/secrets;
- external accounts;
- desktop/browser sessions;
- system processes/services;
- signed capabilities and security keys;
- approval integrity;
- audit/event history;
- learned skills;
- model/provider data egress.

## Adversaries

1. Malicious or prompt-injected content read by the agent.
2. Compromised/incorrect reasoning model output.
3. Malicious repository/project instructions.
4. Local process attempting to forge/steal authority.
5. Stale/replayed action after crash.
6. Skill poisoning.
7. Target substitution/PID reuse/path traversal.
8. Over-broad browser or secret scope.
9. User error during consequential automation.

## Main defenses

### Prompt injection

- observation provenance remains untrusted;
- model cannot directly execute;
- canonical policy outside model;
- project commands are approval-gated;
- later browser/desktop content uses the same taint model.

### Forged authority

- Ed25519 signature;
- exact action hash;
- executor/device/audience binding;
- short expiry;
- one-use nonce;
- durable replay record.

### Scope escape

- task filesystem roots;
- ResourceScope claims;
- direct argv execution, not shell strings;
- path resolution before policy;
- planned symlink/adversarial tests.

### Duplicate side effects after crash

- action journal;
- `COMMIT_STATUS_UNKNOWN`;
- external-state reconciliation before retry;
- native idempotency keys where supported.

### PID substitution

- process termination can bind observed `create_time` as well as PID.

### Secret leakage

- first release environment inspection exposes keys, not values;
- cleaned sandbox env;
- later origin-bound Secret Broker;
- no secret retention in logs/model context by policy.

### Self approval

- approvals stored outside planner;
- later UI security surfaces are excluded from desktop automation;
- approval decision is keyed to exact action ID.

## Security tests in first release

Automated tests cover:

- planner cannot lower high-risk capability;
- untrusted project start requires approval;
- token action binding;
- token replay rejection;
- lease conflicts/fencing;
- missing-secret diagnosis stops without inventing values;
- action journal unknown-commit state;
- end-to-end exact approval for port-conflict repair.

The evaluation catalog also reserves cases for prompt injection, target substitution, path/symlink escape, approval spoofing, skill poisoning and other later-version security tests.
