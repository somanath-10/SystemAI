# Open-Source Reference Matrix

This document records how the projects discussed during SystemAI design influence the architecture. SystemAI should borrow ideas or use pinned adapters rather than making any one external agent framework its foundation.

| Project / ecosystem | Adopt | Reject / constrain |
|---|---|---|
| Microsoft UFO / UFO2 / UFO3 Galaxy | explicit stages, task DAG/constellation, state-machine ideas, future device capability assignment | do not make UFO the first release framework; do not introduce an early agent swarm |
| Cua | initial ComputerExecutor backend, native-driver separation, stable macOS TCC identity, bounded manifests, exact app/window targets, doctor/readiness | Cua is not the global SystemAI security kernel |
| Agent-S | separate reasoning/grounding, visual reflection, bounded screenshot history, local grounding research | no arbitrary model-generated Python/Bash `eval`/`exec` on host |
| Open Interpreter / Codex-style runtime | sandbox policy separated from approval policy, read-only/workspace-write/elevated modes, provider profiles, fail closed | do not use generic shell as privileged desktop authority |
| Agent Desktop | accessibility-first semantic controls, compact agent-oriented state, selectors/refs | coordinates only as fallback |
| Open Computer Use | small semantic desktop tool surface, local/background-first patterns, permission onboarding | keep behind SystemAI policy/executor contracts |
| agent-ctrl / archived Computer Use Protocol | compact ARIA-like normalized accessibility, snapshot-scoped refs, fresh resolution | older protocol is historical; do not depend on stale refs |
| Browser Use / Browser Harness / BrowserCode | persistent CDP, reusable task/domain helpers, browser experimentation | generated helpers must be sandboxed/scoped before qualification |
| Stagehand | cached deterministic browser actions, inference-free replay, self-healing only on drift | no AI call on every known step |
| Skyvern | browser workflow/CV fallback ideas, provider flexibility | avoid screenshot-heavy multi-call default; licensing review needed |
| OpenHands | action/observation/event separation, sandboxed code runtime, reproducible environments | host authority stays outside coding worker |
| OpenClaw-like gateway patterns | trusted host gateway + risky execution sandbox | sandbox is not a substitute for canonical capability policy |
| OpenAdapt / OpenAdapt Flow | record -> review -> compile -> qualify -> replay; verified handoffs | successful trajectory is not automatically a trusted skill |
| OmniParser | optional local screen parser when accessibility is incomplete | perception only; inspect model/code licenses independently |
| UI-TARS / OpenComputer-style projects | local VLM grounding feasibility and supervised modes | never use local VLM as authority; benchmark before routing |
| macOS Harness / agent-computer-use | native interaction primitives and accessibility references | broad agent authority does not replace SystemAI policy |
| OSWorld / OSWorld V2.x | desktop regression benchmark | not a substitute for project-specific tests |
| Windows Agent Arena | Windows evaluation | later platform phase |
| BrowserGym / WebArena / VisualWebArena / WorkArena | browser evaluation | benchmark only |
| AppWorld / AppWorld-UL | state-based success, collateral effects, confirmation/clarification evaluation | benchmark only |
| AgentDojo | tool-agent prompt-injection evaluation | benchmark/security reference |
| DoomArena | adversarial computer/browser agent evaluation | benchmark/security reference |
| CaMeL-style research | data/control-flow isolation and capability-aware prompt-injection defenses | research influence, not assumed production security kernel |

## Architectural synthesis

The first release synthesis is:

```text
UFO/Galaxy        -> DAG concepts
Cua               -> future desktop driver
Agent-S           -> future visual recovery concepts
Open Interpreter  -> sandbox/approval separation
Agent Desktop/
Open Computer Use/
agent-ctrl        -> semantic accessibility protocol ideas
Stagehand         -> deterministic browser cache
OpenHands/OpenClaw-> isolated coding/tool runtime
OpenAdapt         -> future skill qualification workflow
SystemAI          -> Security Kernel + provenance + signed authority + verification + crash safety
```

## Dependency policy

Before bundling any external project/model:

1. pin exact version/commit;
2. record code license;
3. separately record model-weight license;
4. security review the exact release;
5. keep it behind a SystemAI adapter;
6. add deterministic tests and a removal/replacement path.
