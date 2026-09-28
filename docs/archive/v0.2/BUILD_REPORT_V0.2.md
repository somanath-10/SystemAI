# SystemAI v0.2 build verification

Generated: 2026-09-25

## Verified in this environment

- Python compileall: PASS
- Automated pytest suite: **17 passed**
- V0.1 file/task end-to-end execution: PASS
- V0.2 semantic desktop DAG integration with deterministic fake Cua backend: PASS
  - semantic application resolution
  - semantic window resolution
  - fresh accessibility snapshot
  - fresh element-token resolution
  - semantic action
  - independent fresh verification
- Bare element-index-without-snapshot rejection: PASS
- Mixed semantic + pixel targeting rejection: PASS
- Screenshot persistence redaction: PASS
- FastAPI `/health`: PASS
- FastAPI `/capabilities`: PASS (**27 capabilities**)
- FastAPI `/desktop/status` disabled-state smoke test: PASS

## Implemented but not executable in this Linux build container

- Live Cua Driver macOS desktop calls.
- macOS Accessibility and Screen Recording TCC permission verification against a real desktop session.
- TextEdit/Finder/Calculator/Chrome live acceptance matrix.
- React/Tauri package build (dependency installation requires external package access in this build environment).
- Playwright browser runtime (optional package/browser binaries are not installed here).
- Live OpenAI planner call (requires optional SDK + user API key).

## Important V0.2 security properties

- The planner may use semantic app/window/element selectors but does not invent ephemeral PIDs/window IDs/tokens/coordinates.
- The desktop executor re-resolves current identities immediately before acting.
- A semantic selector matching zero or multiple windows/elements fails closed.
- Element tokens come from a fresh window snapshot in the same SystemAI desktop session.
- High/critical actions still pass through the central policy/approval path.
- Driver output never bypasses independent verification.
- Screenshot/base64 and oversized payloads are redacted before audit/long-term memory persistence.
- No generic privileged shell or root executor is enabled.

## Next validation target

Run `docs/MACOS_DESKTOP_V02.md` and `scripts/desktop_doctor.py` on the target Mac, then execute the V0.2 live acceptance matrix before starting V0.3 visual grounding.
