# SystemAI holographic workspace

The supplied Jarvis interface is now the main SystemAI UI. Claude SDK/authentication and browser-side API keys have been removed. OpenAI Responses, speech, search and images go through the Python runtime; additional speech providers and configured MCP tools use the Node bridge and shared Python budget ledger.

## Start

From the repository root, install Python into `.venv` (`pip install -e '.[dev,browser]'`), then run:

```bash
npm --prefix jarvis-main ci
npm --prefix apps/desktop/ui ci
make dev
```

Node 20.19.x or 22.12+ is required. Open http://127.0.0.1:5802. The launcher starts/reuses the compatible API on 8765 and starts the bridge on 8787. It will not silently switch UI ports. Use Message for typed interaction and Task Center for diagnosis, canonical approvals, browser/desktop tasks, local inference, memory and cost controls.

## Retained features

- Three.js/GLSL reactor, particles, orbiting media, phase colours, animation, boot sequence, sounds and music.
- Continuous voice detection, wake phrase, transcript burst assembly, follow-up listening, barge-in, queued speech and mouth/reactor animation.
- Browser speech fallback, optional browser-local Kokoro, OpenAI/ElevenLabs speech, Deepgram STT with diarization, Cartesia TTS, and selectable Sarvam STT/TTS.
- Camera stills, watch mode and rolling-frame grids; local hand tracking and clap gestures, with browser microphone/camera permission.
- Movable/resizable blades, data panels, HTML reader, image/audio/video display, media orbits and UI theme/reactor/effect tools.
- Remote media/image/reader proxies with target validation; bounded local media access.
- Configurable stdio/Streamable HTTP/legacy SSE MCP connectors, tool discovery and function execution.
- Chrome page observation, search, console/network inspection and screenshots; input actions go through signed SystemAI tasks.

The old private Claude-in-Chrome protocol is replaced by native CDP at an explicitly configured loopback endpoint. No Claude extension, Claude subscription or Anthropic key is required. The original unused Porcupine packages are not a working offline wake-word detector; normal wake detection uses the selected transcription pipeline.

## Controls

| Control | Action |
| --- | --- |
| INITIALISE | Start audio/boot sequence |
| Message | Typed request, without microphone dependency |
| Task Center | Open SystemAI task controls |
| Hey Jarvis / Space | Wake / begin listening |
| Speak while answering | Interrupt and start a new turn |
| Escape | Interrupt and return to standby |
| V / D / T | Cycle voice / diagnostics / audio test |

## Configuration and limits

Use the repository's private `.env`, with placeholders in `../.env.example`. Never set any provider key in a `VITE_*` variable. Frontend overrides belong in `../apps/desktop/ui/.env.local`; see `.env.example` here.

OpenAI requires enable=true, key, compatible model, current verified token rates and positive spend/call caps. Speech additionally requires enable=true and positive STT/TTS call estimates. Search requires a tool-call estimate; images require an image model and call estimate. Pricing is user-supplied accounting, not a provider-enforced billing guarantee. Ambiguous cloud requests hold their reservation. New sessions inherit current budgets; existing task budgets never increase automatically.

Copy `../config/mcp.example.json` to ignored `../config/mcp.json` and enable only trusted connectors. Supply each connector's credentials/URL through private environment settings. Original connector categories are configuration examples; none is installed, authenticated or paid for automatically. Only explicitly allowlisted read-only tools are exposed, and each call reserves its configured ceiling in the shared Python budget. Tool-name classification cannot prove a remote tool's semantics: review each connector before enabling it. Direct external mutations remain disabled.

Optional `SYSTEMAI_CHROME_CDP_URL` must point to an isolated Chrome debug profile, never your personal profile. Direct CDP is observation-only. Actions use the signed SystemAI service and Task Center approvals. Every enabled trusted MCP connector requires exact read-only `allowedTools` names and a positive `usdPerCall` estimate; costs share the conversation ledger. The direct-write bypass was removed.

Browser STT may use the browser vendor's online service. Kokoro and MediaPipe models download on demand and need connectivity/cache; hands, camera, microphones and real audio output require hardware validation. The bundled Tauri shell and local HTTP services are development interfaces, not authenticated production IPC.

## Verification and credits

`make check` runs compilation, Python/UI tests, bridge tests (including real isolated Chrome), UI build, Rust kernel tests and acceptance fixtures. `npm run setup` reports provider readiness without printing credentials.

Jarvis UI: MIT, copyright 2026 Aditya Dewaskar; see [LICENSE](LICENSE). Music: Kevin MacLeod, CC BY 4.0; see [audio credits](public/audio/CREDITS.md). Both credits are accessible in the Message modal. Third-party libraries retain their own licenses. See [complete workflow](../docs/guides/ASSISTANT_WORKFLOW.md) for coverage and readiness.
