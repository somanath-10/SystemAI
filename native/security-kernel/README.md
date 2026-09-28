# Rust Security Kernel

This crate is the production-target authority boundary for SystemAI. The first release Python runtime includes a strict reference kernel with the same intended decisions so the end-to-end release can be tested in environments that do not contain Rust.

Responsibilities:

- canonical capability/risk/reversibility decisions;
- provenance and scope validation;
- approval verification;
- Ed25519 capability signing;
- nonce/replay constraints;
- future Secret Broker authorization;
- security audit events.

The planner never owns authority. A model-supplied `risk_hint` cannot lower the kernel's canonical risk.

## Local build

```bash
cargo test
cargo build --release
```

The current crate contains a development JSON-lines adapter. The production V2 integration will use authenticated Unix-domain socket / named-pipe IPC and will keep the signing private key inside the trusted kernel process.

The privileged helper is a separate service and must never accept arbitrary prompt text or unrestricted shell commands.
