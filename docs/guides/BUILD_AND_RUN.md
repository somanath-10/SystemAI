# Build and Run

## 1. Python runtime

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
systemai doctor
pytest
```

## 2. Run diagnosis CLI

```bash
systemai diagnose /absolute/path/to/project
```

The CLI pauses and prints the canonical approval summary for consequential actions.

Noninteractive runs stop at approval rather than auto-approve:

```bash
systemai diagnose /path/to/project --non-interactive
```

## 3. Local API

```bash
systemai-api
```

Routes:

- `GET /health`
- `GET /capabilities`
- `POST /tasks/developer-diagnosis`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/approval`
- `POST /tasks/{task_id}/pause`
- `POST /tasks/{task_id}/resume`
- `POST /tasks/{task_id}/take-control`
- `POST /tasks/{task_id}/cancel`
- `GET /approvals/{approval_id}`
- `GET /events`

The HTTP API is a development interface. Production architecture uses local authenticated IPC.

## 4. Command Center

```bash
cd apps/desktop/ui
npm install
npm run dev
```

Configure `VITE_SYSTEMAI_API` if the API is not on `http://127.0.0.1:8765`.

## 5. Rust Security Kernel

On a Rust-enabled host:

```bash
cd native/security-kernel
cargo test
cargo build --release
```

## 6. Acceptance demo

```bash
python scripts/run_v1_acceptance.py
```

This creates a temporary project, creates a deliberate port conflict, lets the runtime diagnose it, approves the exact repair in the test harness, starts the intended app and verifies its health.
