# Dependency and License Inventory

## first release direct Python runtime dependencies

The authoritative version bounds are in `pyproject.toml`.

- cryptography — capability signing and verification
- FastAPI — development/debug control API
- httpx — bounded HTTP health probes
- Pydantic — versioned contracts
- pydantic-settings — configuration support
- psutil — process/system inspection
- uvicorn — development API server

Optional:

- Playwright — future browser executor integration
- OpenAI Python SDK — optional future planner/provider adapter
- pytest / pytest-asyncio — tests

## Desktop UI

The pinned frontend versions are in `apps/desktop/ui/package.json`. The Tauri Rust crate uses the Tauri 2 major release line.

## Native security-kernel source

`native/security-kernel/Cargo.toml` declares the Rust crate dependencies used by the production security-kernel implementation source.

## Open-source architecture references

Reference projects are not automatically runtime dependencies. See `docs/research/OPEN_SOURCE_REFERENCE_MATRIX.md` for the adoption/rejection decision for UFO/Galaxy, Cua, Agent-S, Open Interpreter/Codex-style runtimes, Agent Desktop, Open Computer Use, agent-ctrl, Browser Harness/Browser Use, Stagehand, Skyvern, OpenHands, OpenAdapt, OmniParser and evaluation projects.

## Distribution policy

- Pin exact releases/commit SHAs before bundling external runtime dependencies.
- Record code license and model-weight license separately.
- Generate a full SBOM before production distribution.
- Do not copy code from reference repositories merely because it is public.
- Preserve required notices when a dependency is distributed.

The `NOTICE.md` file identifies architecture references; it does not claim their code is bundled.
