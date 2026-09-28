# Development Guide

## Requirements

- Python 3.11+
- Git
- Node 20+ for Command Center development
- Rust stable for compiling Tauri and the production Security Kernel
- optional Playwright/Cua in later versions

## Python setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Useful commands

```bash
systemai version
systemai doctor
systemai diagnose /path/to/project
systemai-api
make test
make acceptance
```

## Runtime data

Default: `~/.systemai/v1/`

Contains:

- SQLite/WAL event/action/approval data;
- Ed25519 development signing key;
- quarantine directory;
- future artifacts.

Do not commit this directory.

## Development architecture rules

1. Planner output is typed.
2. Planner risk is not authoritative.
3. Every side effect uses ExecutionGateway.
4. Consequential side effects require a capability token.
5. Executors verify exact action binding.
6. Every action declares verification.
7. Unknown/ambiguous state fails closed.
8. Never add a generic `run_shell(any_string)` capability.
9. Repository/web/UI/terminal content is untrusted data.
10. Add evaluation/security tests with each new capability.

## Fast feature workflow

For a new executor:

```text
contract
 -> capability metadata
 -> executor
 -> verifier
 -> policy tests
 -> integration test
 -> eval catalog
 -> docs
```

This order prevents UI/planner code from becoming coupled to OS implementation details.

## Rust kernel

```bash
cd native/security-kernel
cargo test
cargo build --release
```

This session's build environment did not include Cargo, so those commands are intended for a Rust-enabled development machine/CI.

## UI

```bash
cd apps/desktop/ui
npm install
npm run dev
```

Start `systemai-api` separately. Tauri integration is under `apps/desktop/src-tauri`.

## Branch strategy

Suggested:

- `main` — always passes core/eval gates;
- `feature/v1-*` — V1 maintenance;
- `feature/v2-desktop-*` — macOS/Cua integration;
- `feature/v2-browser-*` — browser profile/CDP;
- security changes always include adversarial tests.

## Dependency policy

For each dependency/model record:

- repository;
- exact version/commit;
- code license;
- model-weight license;
- purpose;
- audit date;
- known risks;
- bundled vs external-service status.

Prefer adapters/dependencies over copying external frameworks into the SystemAI core.
