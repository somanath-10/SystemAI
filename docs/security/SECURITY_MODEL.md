# SystemAI V1 Security Model

## Principle

AI decides intent; trusted code controls authority.

The reasoning plane may be wrong, manipulated, or uncertain. It never receives unrestricted host authority.

## Canonical action path

```text
ActionIntent
 -> capability exists?
 -> scope valid?
 -> provenance/taint analysis
 -> canonical risk
 -> canonical reversibility
 -> approval policy
 -> signed capability
 -> exact executor
 -> fresh verification
```

## Planner hints are non-authoritative

The planner can propose `risk_hint`, `expected_reversibility` and an executor preference. The Security Kernel recomputes the authoritative values from the registered capability and operation semantics.

For example, `process.terminate` remains high risk even if the planner labels it low risk.

## Provenance / taint

Trusted authority sources:

- authenticated user instructions;
- system/admin policy;
- capability definitions;
- future qualified and signed skills.

Untrusted observations:

- repository/project contents unless explicitly promoted by user review;
- web pages;
- emails;
- documents/PDFs;
- terminal/log output;
- downloaded files;
- clipboard/UI text/external messages.

V1 carries provenance metadata into actions. Sensitive consequential operations derived from untrusted content require explicit approval.

A successful LLM transformation does not declassify data.

## Capability tokens

V1 uses Ed25519 signatures in the executable Python reference runtime and includes a Rust implementation source for the production kernel boundary.

Claims bind:

- key ID;
- audience;
- exact executor;
- device;
- session/task/node/action;
- hash of the exact action;
- capability name;
- resource scope;
- parameter hash;
- approval record;
- provenance constraints;
- issue and expiry time;
- nonce;
- single-use semantics.

Executor replay is rejected both by verifier memory and by the durable used-nonce table.

## Scope

Filesystem mutations are authorized only within task roots. V1 does not expose a general root/admin shell.

Process termination is PID-bound and can include the observed process creation time to detect PID reuse.

## Approvals

Approvals are generated from canonical kernel information, not model-generated prose.

A record contains the exact capability, target, canonical risk/reversibility, task/node and reason.

Later desktop versions must hard-deny automation of:

- SystemAI approval/security windows;
- Touch ID / Windows Hello;
- password-manager prompts;
- UAC/security surfaces;
- privacy permission panes.

## Secrets

V1 does not provide a raw-secret tool. Environment inspection compares **key names only**; values are intentionally not returned.

Later Secret Broker design is origin/application/usage bound and uses the OS secure store.

## Shell/code

V1 sandbox commands:

- must be `argv: list[str]`;
- use `shell=False` semantics;
- cannot contain shell-metacharacter command strings;
- are limited to an explicit binary allowlist;
- use a cleaned environment that drops obvious secret variables;
- require an isolated Docker backend (configure `SYSTEMAI_SANDBOX_IMAGE` for the project runtime) with network disabled;
- fail closed when the requested isolation profile cannot be technically enforced.

A generic unrestricted host shell is not a V1 tool.

## Kill switch / takeover

Task API includes pause, cancel and take-control states. V2 desktop integration will connect these states to actual pointer/keyboard lease relinquishment.

## Production Rust boundary

`native/security-kernel/` contains the source for the production security authority. In this build environment Rust was unavailable, so the Python reference implementation is what is executable/tested locally. Deployment should not treat Python ownership of the private signing key as the final production trust boundary.
