# SystemAI Master Architecture and Implementation Blueprint

**Status:** Source-of-truth design after review of the current SystemAI V0.2 codebase and public open-source computer-use / desktop-agent / browser-agent / coding-agent ecosystems.

**Objective:** Build a local-first autonomous operating-intelligence layer that can understand a user's goal, observe and model the computer, plan cross-application workflows, operate applications and system resources through the safest available interface, verify results independently, recover from failures, learn reusable procedures, monitor the machine event-by-event, diagnose problems, and escalate to cloud AI only when local/deterministic methods are insufficient.

---

## 1. Product definition

SystemAI is not a mouse-clicking bot and not a single unrestricted LLM process. It is a layered operating-intelligence system composed of:

1. A user-facing command center.
2. A reasoning and orchestration plane.
3. A cost/model routing plane.
4. A capability and world-model plane.
5. A trusted policy / authorization kernel.
6. A replaceable execution plane for APIs, browsers, desktop accessibility, files, processes, shell, and remote devices.
7. An observation and perception plane.
8. An independent verification plane.
9. Recovery and autonomous diagnosis.
10. Memory, skills, workflow compilation, and learning from successful trajectories.
11. Continuous event-driven monitoring and automation.
12. Audit, observability, privacy, and evaluation.

The main product promise is:

> The user gives a goal, not a sequence of clicks. SystemAI determines the required applications and capabilities, executes the smallest safe plan, verifies the final state, and learns successful procedures so repeated work gets cheaper and more reliable.

---

## 2. Required user use cases

The architecture must support all of the following without being redesigned later.

### 2.1 Desktop and application control

- Discover installed/running applications.
- Launch, focus, close, minimize, maximize, switch, and inspect applications and windows.
- Read accessibility/UI trees.
- Search application controls by semantic properties.
- Click, double-click, invoke secondary actions, drag, scroll, select, set values, type text, use shortcuts, and operate menus.
- Use screenshots/vision only when structured interfaces are inadequate.
- Operate media controls such as play, pause, volume, seek, open file, etc., when exposed by an application.
- Support macOS first, then Windows and Linux without changing SystemAI Core.

### 2.2 Browser control

- Reuse logged-in browser sessions when authorized.
- DOM/CDP/Playwright-first navigation and actions.
- Tabs, forms, downloads, uploads, scrolling, extraction, network state, cookies/session use where permitted.
- AI-assisted/self-healing fallback for changing websites.
- Convert repeated browser trajectories into deterministic cached helpers/skills.

### 2.3 Files and system resources

- Search/read/write/copy/move/rename files and directories.
- Observe file-system changes.
- Inspect/launch/stop processes and services under policy.
- Inspect ports, networks, disk, CPU, RAM, environment, logs, devices, clipboard, notifications, and system settings.
- Use system APIs and typed tools instead of generic shell commands whenever possible.

### 2.4 Coding and technical diagnosis

Example user request: "Find why this project is not working and fix it."

SystemAI should be able to inspect:

- source files and Git state,
- package manifests and lock files,
- environment/configuration,
- processes and ports,
- containers/services,
- databases,
- logs and stack traces,
- dependency versions,
- tests and health endpoints.

It then forms hypotheses, performs bounded tests, proposes/remediates the highest-confidence cause, restarts/retests, and verifies the result.

### 2.5 Cross-application workflows

Example:

- find a spreadsheet,
- calculate metrics,
- create a chart,
- add it to a report,
- export PDF,
- create an email draft,
- request approval,
- send,
- verify delivery/draft state where possible.

These workflows must be represented as a task DAG, not a single opaque agent loop.

### 2.6 Continuous autonomous monitoring

SystemAI should react to events instead of continuously querying an LLM:

- process crash,
- service failure,
- file change,
- download complete,
- low disk,
- unusual CPU/memory,
- network change,
- app/window events,
- permission changes,
- automation schedules/conditions.

Known events should trigger deterministic rules or skills. AI is invoked only when interpretation is needed.

### 2.7 Voice

- Local VAD and optional wake-word.
- Local speech-to-text by default.
- Local text-to-speech by default.
- Cloud STT/TTS/realtime voice only for quality, language, latency, or confidence escalation.

### 2.8 Local-first privacy and low operating cost

- Idle SystemAI makes zero cloud model calls.
- Known actions should make zero model calls.
- Repeated learned skills should usually make zero cloud calls.
- Local models handle routing/routine reasoning/grounding where hardware allows.
- Premium APIs solve hard/ambiguous/high-impact cases or act as teachers that create reusable local skills.

---

## 3. Design principles

### 3.1 AI decides intent; trusted code controls authority

Never allow the model itself to possess unrestricted operating-system authority.

Correct:

User -> Planner -> typed ActionIntent -> Policy Kernel -> capability token -> Executor -> OS

Incorrect:

LLM -> unrestricted root/admin shell

### 3.2 Prefer structured control over visual control

Permanent executor preference:

1. Official application/service API.
2. MCP/plugin/integration.
3. Native OS/application API.
4. Browser DOM/CDP/Playwright.
5. Accessibility API.
6. Known keyboard shortcut.
7. Local vision/grounding.
8. Raw pointer/coordinate interaction.

Vision and coordinates are recovery tools, not the default interface.

### 3.3 Fresh observations, not stale UI handles

Desktop elements are ephemeral. The planner describes semantic intent; the trusted executor resolves the current app/window/snapshot/ref immediately before acting.

A UI element reference is valid only for the observation/snapshot that created it unless the backend explicitly guarantees otherwise.

### 3.4 Independent verification

"Command returned success" is not the success criterion.

Examples:

- Saving a document -> verify file path/content.
- Starting a backend -> call health endpoint / inspect process and port.
- Setting a text field -> fresh accessibility observation and compare value.
- Browser navigation -> verify URL/DOM/state.
- Database write -> query resulting state.

### 3.5 Fail closed on ambiguity

If target selection returns zero or multiple matches, do not guess. Re-observe or ask/re-plan.

### 3.6 Separate reasoning from execution

Reasoning plane can be prompt-injected or wrong. Execution plane remains typed, policy-scoped, permissioned, and independently verifiable.

### 3.7 Local-first, escalation-based intelligence

Deterministic code -> cached skill -> small local classifier -> local LLM/VLM -> specialist inexpensive API -> premium cloud reasoner.

### 3.8 Learn repeatable work

Once a costly AI-generated trajectory succeeds repeatedly, compile it into a parameterized skill and replay it without expensive reasoning.

### 3.9 Event-driven monitoring

Do not continuously send screenshots/system state to an LLM. Use OS events, watchers, rules and thresholds. AI processes only meaningful exceptions.

### 3.10 One source of truth for state

The task graph, policy state, approvals, observations, effects and audit trail must be durable and replayable. Do not spread critical state across hidden agent prompts.

---

## 4. Open-source architecture review and what SystemAI should adopt

The project should use architecture ideas and clearly licensed dependencies/adapters rather than copying entire frameworks into the core.

### Microsoft UFO2 / UFO3 Galaxy

Best ideas to adopt:

- Supervisor/host vs app/device agent separation.
- Explicit processing stages: collect data -> reason -> execute -> memory.
- Explicit state machines rather than implicit LLM lifecycle.
- Dynamic task DAG / Task Constellation for dependencies and parallel work.
- Capability-aware device assignment.
- Distributed device-agent protocol as a future multi-device model.

Do not make UFO the SystemAI foundation. SystemAI must be OS-neutral and preserve its own policy/execution contracts.

### Cua

Best ideas to adopt:

- Dedicated native computer driver separated from model runtime.
- Cross-platform desktop execution.
- macOS daemon with stable TCC permission identity.
- Standard/bounded/unrestricted permission modes.
- Capability manifests that the agent cannot widen through a tool call.
- Exact app/window targets and background-first interaction.
- Driver doctor/readiness checks.

SystemAI should treat Cua as the primary initial desktop backend behind a `ComputerExecutor` interface, not as a dependency visible throughout the core.

### Agent-S

Best ideas:

- Separate main reasoning and grounding models.
- Visual reflection using previous action + previous/current screenshot.
- Local vLLM support.
- Bounded image trajectory/context.

Do not copy unsafe model-output-to-code execution patterns. Visual grounding must output a typed ActionIntent; no model-generated Python should be `eval`/`exec`'d on the host.

### Open Interpreter / Codex-derived runtime patterns

Best ideas:

- Separate sandbox policy from approval policy.
- Read-only / workspace-write / dangerous modes.
- Fail closed when sandbox enforcement is unavailable.
- Provider/model profiles.
- Tool router/registry.
- Lifecycle hooks.
- Granular permission amendments for filesystem/network/shell.

Use these ideas for SystemAI's coding/shell runtime, not for privileged desktop control.

### Agent Desktop

Best ideas:

- Accessibility-first structured JSON/compact output.
- Ref/selector-based deterministic targeting.
- Token-efficient observations designed for agents.
- Cross-platform native accessibility normalization.

### Open Computer Use

Best ideas:

- Small semantic tool surface.
- Accessibility-first and local execution.
- Background-first input.
- Guard high-risk apps/input/focus operations.
- First-run doctor and permission onboarding.

### agent-ctrl / Computer Use Protocol

Best ideas:

- Normalize cross-platform accessibility to a compact ARIA-like schema.
- Snapshot-scoped actionable refs.
- Structural/scope refs for windows/dialogs/containers.
- Re-resolve refs at action time.
- Reject actions against non-actionable structural refs.
- Compact accessibility representation to reduce model context dramatically.

The older Computer Use Protocol repository is archived; use it as a protocol-design reference, not a dependency. `agent-ctrl` is the newer implementation reference.

### Browser Harness / BrowserCode / Browser Use

Best ideas:

- Persistent CDP connection.
- Browser operations kept separate from native desktop operations.
- Agents may write reusable domain/task helpers into an isolated workspace.
- Browser skills improve with repeated work.

Do not expose unconstrained browser script execution to untrusted page content without sandbox/policy controls.

### Stagehand

Best ideas:

- Hybrid code + natural-language browser automation.
- Cache successful actions.
- Run deterministic cached path without model inference.
- Invoke AI/self-healing only when page drift breaks the known path.

This should heavily influence SystemAI browser cost control.

### Skyvern

Useful ideas:

- Playwright + AI/CV hybrid.
- Browser workflow builder.
- Multi-model/provider support including local/OpenAI-compatible endpoints.

Important lesson: screenshot-heavy browser agents can make several model calls per step. SystemAI should avoid that default by preferring DOM/CDP and cached skills.

### OpenHands

Best ideas:

- Action/Observation event model.
- Sandboxed runtime for code/shell/browser development tasks.
- Clear agent/runtime separation.
- Reproducible execution environments.

SystemAI should use an isolated code/shell runtime for untrusted technical work while keeping the trusted desktop driver on the host.

### OpenClaw

Best idea:

- Trusted gateway remains on the host; risky tool execution moves into a sandbox.

This maps cleanly to SystemAI's trusted execution gateway + sandboxed coding workers.

### OpenAdapt / OpenAdapt Desktop / OpenAdapt Flow

Best ideas:

- Record -> review -> compile -> replay workflows.
- Governed repair/teach when replay halts.
- Independent verification of results.
- Local-first recording and review before egress.
- Compose multiple surface-specific workflow bundles with explicit handoff values.

SystemAI should add a Demonstration Recorder and Skill Compiler influenced by this pattern.

### OmniParser

Useful as an optional local perception fallback:

- Convert screenshots to structured candidate UI elements when accessibility is incomplete.

Keep it optional and review model/repository licensing before bundling specific detector weights.

### OpenComputer / UI-TARS-style local computer use

Best ideas:

- Local-first vision-language execution.
- OpenAI-compatible model boundary.
- Explicit Ask First/supervision modes.

Use this as evidence for SystemAI's local VLM fallback, not as the primary action mechanism.

### Benchmark ecosystems

Use them for evaluation, not production dependencies:

- OSWorld: real desktop tasks.
- Windows Agent Arena: Windows tasks.
- BrowserGym + WebArena/VisualWebArena/WorkArena: browser/knowledge-work tasks.
- AppWorld: complex multi-app API tasks with state-based success and collateral-damage checking.
- AppWorld-UL: user-in-the-loop clarification/confirmation evaluation.

---

## 5. Target architecture

```text
USER / EXTERNAL TRIGGERS
  |-- text
  |-- local voice
  |-- API
  |-- scheduled automation
  |-- system event
  v
INPUT + TRUST GATEWAY
  |-- identity/session
  |-- input normalization
  |-- source trust label
  |-- local VAD/STT for voice
  v
GOAL + ROUTING LAYER
  |-- known skill / deterministic route lookup
  |-- ModelRouter
  |-- CostController
  |-- ConfidenceEngine
  v
REASONING / ORCHESTRATION PLANE
  |-- Goal Interpreter
  |-- Supervisor
  |-- Planner
  |-- Task DAG + state machine
  |-- Capability Graph
  |-- Context Builder
  |-- Memory Retriever
  |-- Skill Registry
  v
TYPED ACTION CONTRACT
  v
TRUSTED SECURITY KERNEL
  |-- schema validator
  |-- risk classifier
  |-- policy engine
  |-- scope validator
  |-- approval service
  |-- secret broker
  |-- capability-token issuer
  v
EXECUTION GATEWAY
  |-- API/MCP executor
  |-- Browser executor (Playwright/CDP)
  |-- Desktop executor (Cua initially)
  |-- Files/process/services/network executors
  |-- Sandboxed code/shell runtime
  |-- Privileged helper (separate Rust service)
  |-- Remote/multi-device executor (later)
  v
OPERATING SYSTEM / APPLICATION / SERVICE
  v
OBSERVATION PLANE
  |-- accessibility compact snapshot
  |-- DOM/CDP
  |-- screenshot diff/crop/hash
  |-- local OCR/CV
  |-- optional local VLM/OmniParser
  |-- files/processes/services/network state
  |-- event collectors
  v
WORLD STATE BUILDER
  v
INDEPENDENT VERIFIER + COLLATERAL-DAMAGE CHECK
  |-- deterministic postconditions first
  |-- semantic local/cloud verification only if required
  +------ success ------> DAG update -> memory -> audit -> next node
  |
  +------ failure ------> Recovery -> alternate executor -> local vision -> diagnosis -> replan -> escalation
```

---

## 6. Major runtime services

### 6.1 Command Center

Technology: React + TypeScript + Tauri 2.

Pages:

- Assistant / new task.
- Current tasks.
- Task graph timeline.
- Approvals.
- Applications/windows.
- Capability graph.
- Skills/workflows.
- Automations.
- System health.
- Events.
- Memory/history.
- Cost dashboard.
- Permissions/security.
- Audit.
- Model/provider settings.
- Device management.

Always display what is happening, why, next action, risk/approval, executor chosen, verification result, and final changes.

### 6.2 Input Gateway

Normalizes:

- text,
- audio transcription,
- API requests,
- automation triggers,
- events.

Each input carries:

- actor identity,
- session,
- trust level,
- origin,
- permissions,
- privacy classification,
- requested budget/quality profile.

### 6.3 Goal Interpreter

Produces a `GoalContract`:

- objective,
- constraints,
- success conditions,
- forbidden effects,
- expected artifacts,
- approval requirements,
- deadline/priority,
- budget profile.

Do not allow the planner to silently redefine these.

### 6.4 Supervisor

Responsibilities:

- select deterministic skill vs AI planning,
- decompose complex goals,
- coordinate specialized agents,
- choose which tasks can run in parallel,
- pause for approvals,
- decide whether all success conditions are satisfied.

### 6.5 Task DAG Engine

Every task node includes:

- node id,
- objective,
- dependencies,
- required capabilities,
- input/output bindings,
- expected postconditions,
- risk class,
- retry/recovery policy,
- time/cost budget,
- executor preference,
- current state.

States:

CREATED -> READY -> RUNNING -> VERIFYING -> COMPLETED

Side paths:

WAITING_FOR_APPROVAL, WAITING_FOR_RESOURCE, RECOVERING, REPLANNING, FAILED, CANCELLED.

Task DAG modifications are validated for cycles and authorization before adoption.

### 6.6 Capability Registry and Capability Graph

Registry defines typed capabilities and their executors.

Graph stores system knowledge:

Nodes:

- Device
- UserSession
- Application
- Window
- UI Surface
- Process
- Service
- Port
- File/Directory
- Project
- Database
- BrowserProfile
- Account
- CredentialReference
- Capability
- Permission
- Tool
- Skill
- Workflow
- Task

Edges:

- HAS_CAPABILITY
- REQUIRES_PERMISSION
- RUNS_PROCESS
- LISTENS_ON
- DEPENDS_ON
- OPENS
- PRODUCES
- READS
- WRITES
- AUTHENTICATES_WITH
- EXECUTABLE_BY
- VERIFIED_BY
- LEARNED_FROM
- USES
- OWNS

Initial storage: SQLite relational graph tables. Do not require Neo4j initially.

### 6.7 Application Registry

Per application:

- bundle/package/executable identity,
- installed/running version,
- supported structured interfaces,
- accessibility quality,
- known shortcuts,
- app-specific API/MCP adapter,
- discovered capabilities,
- learned skills,
- risk restrictions.

Unknown app flow:

metadata -> accessibility/menu inspection -> safe capability inference -> optional supervised exploration -> candidate adapter/skill -> tests -> register.

---

## 7. Core action protocol

### ActionIntent

Model/planner emits semantic intent, not native handles.

Fields include:

- action_id
- task/node id
- capability
- semantic target
- parameters
- expected result/postcondition
- risk level
- reversibility
- resource scope
- elevation requirement
- proposed executor preference
- provenance/model/skill id

### Fresh Target Resolution

Desktop example:

Planner target:

- app bundle id = TextEdit
- window title = Untitled
- role = text area
- accessible name = Editor

Trusted executor:

1. resolve current process,
2. resolve exact window,
3. take fresh accessibility snapshot,
4. find exactly one matching actionable ref,
5. obtain snapshot-scoped token,
6. perform action,
7. invalidate/refetch after relevant UI change.

### ActionResult

Should distinguish:

- performed vs rejected vs failed,
- effect confirmed vs suspected no-op vs unverifiable,
- verification evidence,
- fallback/escalation used,
- side effects/warnings,
- timing and cost.

Do not use a single `success: true` flag as the semantic outcome.

---

## 8. Security architecture

### 8.1 Trust boundary

Trusted instructions:

- authenticated user instruction,
- system/admin policy,
- signed/reviewed skill,
- capability definitions.

Untrusted observations:

- webpage content,
- email body,
- document/PDF,
- terminal output,
- downloaded file,
- application UI,
- clipboard,
- external message.

Untrusted text never becomes a higher-authority instruction merely because an LLM read it.

### 8.2 Security Kernel

Every action path:

ActionIntent -> schema validation -> capability registered? -> resource scope -> risk -> policy -> approval if required -> short-lived capability token -> executor.

### 8.3 Permission profiles

Suggested profiles:

- Observe Only.
- Personal Standard.
- Workspace Automation.
- Bounded App Workflow.
- Developer Sandbox.
- Approved Elevated Maintenance.

No normal profile should mean unrestricted admin authority.

### 8.4 Privileged Helper

Separate Rust process/service.

It receives only:

- signed/verified operation,
- capability token,
- approved scope,
- expiration/nonce.

It does not receive prompts or arbitrary model text.

### 8.5 Secret Broker

The model sees credential references, never raw secrets unless unavoidable.

Example:

`credential_ref: github_main`

The trusted broker resolves/fills it through OS keychain or vault. Secret values are redacted from model context, logs, screenshots where possible, and audit payloads.

### 8.6 Coding/shell sandbox

Run code/shell tasks in a separate sandbox by default.

Profiles:

- read-only,
- workspace-write without network,
- workspace-write with allowlisted network,
- explicitly approved elevated host operation.

Compound shell commands are parsed/authorized segment-by-segment where possible. Generic unrestricted host shell is not part of normal agent tools.

### 8.7 Driver capability manifests

Desktop driver should run in bounded mode when possible, restricting:

- reachable applications,
- allowed origins,
- directories,
- input/focus/global interaction,
- dangerous surfaces.

The AI cannot expand the manifest itself.

---

## 9. Cost Intelligence architecture

This is a first-class subsystem.

### 9.1 Inference tiers

Tier 0 - deterministic/rules/skills

- no model
- OS APIs, accessibility, DOM, files, process checks, regex/parsers, scripts.

Tier 1 - tiny local intelligence

- intent classifier,
- risk/helpfulness classifier,
- embedding/reranking,
- anomaly scoring.

Tier 2 - local LLM

- routine planning,
- summarization,
- log/error interpretation,
- skill parameterization.

Tier 3 - local VLM/grounder

- visual UI grounding,
- screenshot semantics when accessibility/DOM fail.

Tier 4 - inexpensive specialist/cloud provider

- high-quality STT/TTS,
- medium reasoning,
- specialized OCR/vision if local unavailable.

Tier 5 - premium cloud reasoner

- hard planning,
- unresolved diagnosis,
- unusual GUI,
- complex document/code reasoning,
- high-impact cases where local confidence is insufficient.

### 9.2 ModelRouter

Inputs:

- task complexity,
- required modality,
- privacy policy,
- risk,
- local hardware capability,
- local model confidence,
- previous failures,
- latency requirement,
- remaining task budget.

Outputs:

- provider,
- model profile,
- reasoning level,
- context/tool set,
- fallback path.

### 9.3 CostController

Per task limits:

- max cloud spend estimate,
- max cloud calls,
- max premium calls,
- max image calls,
- max audio seconds,
- token/context limits,
- latency/time budget.

Track actual/estimated:

- model calls,
- input/output/cached tokens,
- image/audio usage,
- provider/model,
- local inference time,
- GPU/CPU time if measurable.

### 9.4 Dynamic tool loading

Do not expose every tool to every model call.

Chrome task -> browser subset.

Backend diagnosis -> process, port, logs, files, shell sandbox subset.

This saves context and reduces incorrect tool selection.

### 9.5 Context compression

Model context should contain:

- GoalContract,
- current relevant DAG nodes,
- compact world state,
- top relevant memory/skills,
- recent failures/effects,
- only currently relevant tools.

Do not replay entire trajectories/screenshots/logs.

### 9.6 Speculative/batched local execution

Allow a model to propose a short sequence of low-risk actions. Execute them one-by-one with deterministic guards and postconditions. Stop immediately on state divergence.

One reasoning call can drive several routine actions.

### 9.7 Skills as a cost cache

If a learned skill matches with high confidence and current preconditions are true, replay it without an LLM. If drift occurs, invoke self-healing/AI only around the broken step, then update/requalify the skill.

---

## 10. Local AI and perception stack

### 10.1 Local model runtimes

Support provider interface over OpenAI-compatible or native clients:

- llama.cpp for broad local CPU/GPU/Apple Silicon inference,
- Ollama for easy end-user installation/model management,
- vLLM for high-throughput Linux/NVIDIA deployments,
- optional other OpenAI-compatible local servers.

Provider implementation must be swappable.

### 10.2 Local embeddings

- Sentence Transformers or compatible local embedding model.
- SQLite + sqlite-vec initially.
- Qdrant only when scale/concurrency justifies it.

### 10.3 Screenshot pipeline

Do not call a VLM on every full screenshot.

Pipeline:

1. capture targeted window/region,
2. perceptual hash,
3. compare with prior frame,
4. identify changed regions,
5. accessibility/DOM lookup,
6. local OCR/CV,
7. crop/resize only relevant region,
8. local VLM/grounder,
9. cloud vision only on escalation.

### 10.4 Compact accessibility representation

Normalize platform accessibility roles to one internal schema inspired by ARIA/CUP.

Example compact representation:

`@e17 btn "Save" [enabled] [press]`

`@s2 dialog "Export"`

Refs are bound to a snapshot id/generation.

Never expose password field contents.

### 10.5 Optional local vision parser

OmniParser-like detector/caption pipeline may provide candidate regions when accessibility is missing. It is not a policy/execution authority; it only proposes perception results.

---

## 11. Voice architecture

Default local pipeline:

microphone -> local VAD -> optional wake word -> local STT -> Input Gateway -> SystemAI -> local TTS.

Recommended local candidates:

- whisper.cpp, especially macOS/Apple Silicon,
- faster-whisper for performant local/server transcription,
- sherpa-onnx for unified local speech/VAD/TTS components,
- Kokoro-family local TTS wrapper where quality/hardware fit.

Cloud escalation:

- difficult accents/noise/languages,
- low confidence,
- premium voice quality,
- realtime conversational mode.

Provider abstraction should permit OpenAI or other specialist APIs without changing the core.

---

## 12. Browser execution architecture

Preferred path:

1. service API/MCP if available,
2. direct CDP/Playwright,
3. known cached browser skill/helper,
4. DOM-accessible natural-language action,
5. browser screenshot/local vision,
6. cloud vision/computer-use escalation.

Browser executor components:

- browser profile/session manager,
- CDP connection,
- DOM snapshot/accessibility,
- download/upload manager,
- network/navigation observer,
- deterministic selectors/helpers,
- site/domain skill registry,
- self-healing mechanism,
- sandbox for generated helper code.

Repeated browser task lifecycle:

AI exploration -> successful action trace -> deterministic helper/skill -> regression replay -> zero/low-model normal runs -> AI repair only on page drift.

---

## 13. Desktop execution architecture

`ComputerExecutor` interface:

- list apps/windows,
- observe app/window,
- launch/focus/close,
- click/invoke,
- set value/type,
- key/chord,
- scroll/drag,
- screenshot,
- wait/state predicates.

Backends:

- CuaExecutor (initial primary),
- optional AgentCtrlExecutor as it matures cross-platform,
- optional OpenComputerUseExecutor,
- NativeMac/NativeWindows/NativeLinux fallback implementations later,
- mock executor for deterministic tests.

macOS production pattern:

SystemAI -> trusted policy -> desktop adapter -> CuaDriver.app daemon -> AX/ScreenCapture/input.

Accessibility/Screen Recording permissions belong to the stable signed driver/application identity, not random Python shells.

---

## 14. Observation and World State

Raw observations are converted into normalized world-state facts.

Sources:

- app/window/accessibility snapshots,
- browser DOM/CDP,
- files and watches,
- process/service/port/network state,
- system health,
- clipboard/notification events,
- screenshots/crops,
- sandbox/tool results.

Each observation includes:

- source,
- timestamp,
- trust classification,
- freshness/generation,
- resource identity,
- sensitivity/redaction metadata.

World State stores current facts such as:

- active app/window,
- running processes/services,
- known project/dependencies,
- changed files,
- current browser URL/tabs,
- current resource health,
- pending approvals/tasks.

---

## 15. Verification architecture

Verification is separate from the executor whenever possible.

Verification priority:

1. State/API/database assertion.
2. Filesystem/process/network assertion.
3. Accessibility/DOM state assertion.
4. Local deterministic image comparison.
5. Local semantic model.
6. Cloud semantic model.

Each node defines expected postconditions before execution.

Also define forbidden/collateral effects. Borrow the AppWorld idea: evaluate start/end state and ensure the requested change occurred without unrelated damaging changes.

Examples:

- "move file" -> destination exists, source absent, hash matches.
- "send email" -> correct recipient/content/attachment, send approval present, sent/draft state confirmed.
- "fix service" -> endpoint healthy, correct process listening, no unrelated service termination.

---

## 16. Recovery engine

Classify failures before retrying:

- stale ref/snapshot,
- target missing,
- target ambiguous,
- occluded element,
- app/window changed,
- permission denied,
- no-op action,
- timeout,
- browser navigation drift,
- network/API failure,
- sandbox restriction,
- verification mismatch.

Recovery ladder:

1. Re-observe and re-resolve target.
2. Retry once if idempotent/safe.
3. Use a different structured executor.
4. Use known skill alternative.
5. Local vision/grounding.
6. Diagnosis/replan.
7. Cloud escalation.
8. User clarification/approval when genuinely necessary.

Never infinite-loop.

---

## 17. Autonomous diagnosis engine

Diagnosis model:

1. Convert symptom into hypotheses.
2. Rank hypotheses by prior/context.
3. Generate low-risk discriminating tests.
4. Run tests through normal policy/execution gateway.
5. Update confidence.
6. Stop when root cause meets threshold or evidence is exhausted.
7. Generate remediation plan.
8. Policy/approval.
9. Execute.
10. Verify the original success condition.
11. Store trajectory as candidate repair skill.

Example backend hypotheses:

- process dead,
- port conflict,
- DB down,
- missing/wrong environment value,
- package mismatch,
- bad recent Git change,
- permission issue,
- disk full,
- network/DNS issue.

Diagnosis engine must never bypass policy just because it is "repairing" the system.

---

## 18. Monitoring and automations

Local collectors publish events:

- app/window lifecycle,
- process/service lifecycle,
- file watchers,
- downloads,
- filesystem capacity,
- CPU/RAM thresholds,
- ports/network,
- permissions,
- device connect/disconnect,
- task/workflow events.

Processing:

Event -> filter/dedupe -> deterministic rule -> known automation/skill -> anomaly classifier -> AI only if unresolved.

Automations are durable objects with:

- trigger,
- condition,
- scope,
- allowed capabilities,
- approval policy,
- budget,
- cooldown/dedupe,
- action workflow,
- audit policy.

---

## 19. Memory and knowledge architecture

### Working memory

Only current task state and recent relevant observations.

### Episodic memory

Past task summaries/outcomes/failures.

### Semantic memory

Stable facts: project paths, application metadata, known dependencies, user-approved preferences.

### Procedural memory

Skills and repair procedures.

### Trajectory store

Detailed action/observation/effect/verification records for debugging/training/skill compilation, with privacy retention controls.

Storage initially:

- SQLite for durable records/graph tables.
- sqlite-vec for local similarity search.
- object/file store for larger redacted artifacts when needed.

Do not send full memory to a model; retrieval selects a small relevant set.

---

## 20. Skill and demonstration architecture

### Skill definition

- name/version,
- purpose,
- parameters,
- preconditions,
- steps/sub-DAG,
- capability scopes,
- expected postconditions,
- recovery alternatives,
- supported app versions/environments,
- test suite,
- provenance and signature/review status.

### Skill Compiler

Successful trajectories -> cluster/generalize -> parameterize variable inputs -> remove incidental UI identities -> construct deterministic skill -> sandbox/replay tests -> policy review -> skill registry.

### Demonstration Recorder

Optional user demonstration flow:

record screen/input/window/app events locally -> user review/redaction -> compile candidate workflow -> replay in safe environment -> verify -> accept as skill.

This should be local by default; no raw recording egress without explicit policy.

---

## 21. Audit and observability

Every significant event records:

- actor/session/task/node,
- goal and action id,
- policy decision,
- approval identity/time,
- capability token id (not secret),
- executor/backend,
- target resource,
- result/effect,
- verification evidence,
- recovery/escalation,
- model/provider and estimated cost,
- latency,
- redactions.

Use append-only/hash-chained audit records initially. Add signing/remote attestation for enterprise deployments later.

OpenTelemetry-style traces should correlate:

input -> plan -> policy -> executor -> observation -> verifier -> memory.

---

## 22. Data model / initial persistence

Suggested SQLite tables:

- tasks
- task_nodes
- task_edges
- actions
- observations
- effects
- verification_results
- approvals
- policies
- capability_tokens_metadata
- capabilities
- capability_graph_nodes
- capability_graph_edges
- applications
- application_versions
- windows_current (ephemeral cache only)
- system_resources
- projects
- events
- automations
- skills
- skill_versions
- skill_steps
- skill_test_runs
- trajectories
- memory_items
- model_calls
- cost_ledger
- audit_events
- provider_profiles
- devices

Sensitive secret material stays in OS keychain/vault, never SQLite plaintext.

---

## 23. Recommended implementation stack

### Desktop UI

- React + TypeScript
- Tauri 2

### Trusted native/security components

- Rust
- privileged helper
- event collectors where native APIs matter
- secure local IPC

### Intelligence/orchestration

- Python 3.11+
- Pydantic typed contracts
- FastAPI for local control/debug API initially
- asyncio
- custom DAG/FSM (already started)

Avoid introducing LangGraph merely for branding; add it only if its persistence/checkpoint semantics materially outperform the custom engine.

### Desktop driver

- Cua adapter initially
- agent-ctrl / open-computer-use optional adapters

### Browser

- Playwright + CDP
- cached/helper skill layer inspired by Stagehand/Browser Harness

### Storage

- SQLite
- sqlite-vec

### Local model layer

- Ollama / llama.cpp for end-user machines
- vLLM for GPU/server installations
- local embedding model

### Speech

- whisper.cpp / faster-whisper
- sherpa-onnx/Kokoro option for TTS

### Vision

- accessibility/DOM first
- OpenCV + local OCR
- optional local OmniParser-like parser
- local VLM grounding

### Observability

- structured logs
- OpenTelemetry-compatible traces/metrics

---

## 24. Repository architecture

```text
systemai/
|-- apps/
|   `-- desktop/
|       |-- src/                  # React UI
|       `-- src-tauri/            # signed desktop shell
|
|-- src/systemai/
|   |-- api/
|   |-- contracts/
|   |-- core/
|   |   |-- supervisor/
|   |   |-- goals/
|   |   |-- task_graph/
|   |   |-- state_machine/
|   |   |-- capability_registry/
|   |   `-- capability_graph/
|   |
|   |-- intelligence/
|   |   |-- model_router/
|   |   |-- cost_controller/
|   |   |-- confidence/
|   |   |-- context_builder/
|   |   `-- providers/
|   |
|   |-- planning/
|   |-- security/
|   |   |-- policy/
|   |   |-- approvals/
|   |   |-- risk/
|   |   |-- capability_tokens/
|   |   |-- secrets/
|   |   `-- prompt_boundary/
|   |
|   |-- execution/
|   |   |-- gateway/
|   |   |-- desktop/
|   |   |-- browser/
|   |   |-- api_mcp/
|   |   |-- filesystem/
|   |   |-- process/
|   |   |-- services/
|   |   |-- network/
|   |   `-- sandbox/
|   |
|   |-- observation/
|   |   |-- accessibility/
|   |   |-- browser/
|   |   |-- screen/
|   |   |-- cv/
|   |   |-- system/
|   |   `-- world_state/
|   |
|   |-- verification/
|   |-- recovery/
|   |-- diagnosis/
|   |-- monitoring/
|   |-- automations/
|   |-- memory/
|   |-- skills/
|   |-- demonstrations/
|   |-- audio/
|   |-- audit/
|   `-- evals/
|
|-- native/
|   |-- privileged-helper/
|   `-- collectors/
|
|-- sandboxes/
|   `-- coding-runtime/
|
|-- config/
|-- tests/
|-- evals/
|-- docs/
`-- scripts/
```

---

## 25. End-to-end runtime algorithm

1. Receive text/voice/API/event.
2. Authenticate actor/session and attach trust classification.
3. Normalize request.
4. Search exact known commands/skills/automations.
5. If deterministic skill covers goal and preconditions pass, skip planning model.
6. Otherwise ModelRouter picks local or cloud planner based on complexity, risk, privacy, confidence and budget.
7. Build immutable GoalContract with success and forbidden-effect conditions.
8. Retrieve only relevant memory/skills/capabilities.
9. Build or modify validated Task DAG.
10. Scheduler selects ready nodes.
11. Capability router lists viable methods ordered by reliability/cost.
12. Planner/skill produces typed ActionIntent.
13. Schema validation and semantic target validation.
14. Security Kernel evaluates capability, scope, risk, permission/elevation and prompt provenance.
15. If needed, request user approval before the consequential action.
16. Issue short-lived capability token.
17. Execution Gateway selects API/MCP/browser/desktop/system/sandbox executor.
18. Executor resolves fresh target identifiers and acts.
19. Observation plane obtains fresh state.
20. Independent verifier tests requested postcondition and forbidden/collateral effects.
21. If verified, commit node success, update world state, memory, cost ledger and audit.
22. If not verified, Recovery Engine classifies failure.
23. Re-observe/retry/alternate structured executor.
24. If still unresolved, invoke local vision or diagnosis.
25. Escalate to cloud model only if confidence/budget/risk rules justify it.
26. Re-plan the affected DAG branch; never restart the whole workflow unnecessarily.
27. Continue until every GoalContract success condition is verified.
28. Produce user-facing result + meaningful changes + unresolved limitations.
29. Analyze successful trajectory for skill compilation.
30. Regression-test candidate skill before enabling autonomous replay.

---

## 26. Example workflow: "Fix why my project is not running"

GoalContract:

- Application reaches healthy state.
- Do not delete data.
- Do not alter security settings without approval.
- Keep changes inside project/workspace unless explicitly approved.

DAG:

A. Identify project/runtime.
B. Inspect recent logs/error output.
C. Check process.
D. Check listening port.
E. Check required services/DB.
F. Check environment/config.
G. Check dependencies/Git changes.
H. Rank root-cause hypotheses.
I. Run discriminating tests.
J. Generate minimal fix.
K. Approval if fix leaves normal workspace scope or has destructive consequence.
L. Apply fix.
M. Restart.
N. Run tests/health check.
O. Verify original success condition.
P. Save repair trajectory as candidate skill.

Most checks are deterministic and local. A model is used primarily for log interpretation, hypothesis formation and code repair when needed.

---

## 27. Example workflow: cross-app report and email

User: "Take yesterday's sales data, build the report, export PDF and send it to X."

DAG:

1. Resolve date and locate data.
2. Validate source file.
3. Parse spreadsheet via direct file library first, not GUI.
4. Calculate metrics programmatically.
5. Generate chart/programmatic report where possible.
6. If an office app/template must be preserved, use app automation/accessibility.
7. Export PDF.
8. Verify PDF exists and expected fields are present.
9. Prepare email draft through provider API/plugin if available, browser otherwise.
10. Verify recipient, attachment and body.
11. Request send approval according to policy.
12. Send.
13. Verify sent state.

This demonstrates the principle: do not use GUI merely because a human would.

---

## 28. Testing and evaluation strategy

### Unit tests

- schema validation,
- DAG cycles/dependencies,
- policy/risk/scope,
- capability tokens,
- redaction,
- cost routing,
- compact accessibility parsing,
- target ambiguity,
- verifier logic.

### Deterministic integration tests

Fake/mock desktop/browser/API backends.

Cover:

- stale refs,
- ambiguous refs,
- changed windows,
- retries,
- approval resume,
- collateral-damage rejection,
- budget exhaustion,
- cloud escalation.

### Real macOS tests

- Finder,
- TextEdit,
- Calculator,
- Chrome,
- VS Code/Terminal where safe.

Validate permission onboarding and signed driver identity.

### Windows

- UIA-native tasks,
- Windows Agent Arena,
- app/dialog edge cases.

### Linux

- AT-SPI tasks,
- common GNOME/GTK/Qt applications,
- accessibility daemon behavior.

### Browser

- BrowserGym,
- WebArena/VisualWebArena,
- WorkArena,
- custom logged-in workflow sandbox.

### API/multi-app

- AppWorld state-based verification,
- AppWorld-UL clarification/confirmation behavior.

### Desktop generalization

- OSWorld in VMs/containers.

### Security/adversarial

- webpage prompt injection,
- malicious email/PDF,
- tool-result injection,
- encoded/obfuscated instructions,
- symlink/path traversal,
- stale capability token,
- attempt to widen driver manifest,
- secret exfiltration,
- dangerous shell compound command,
- high-risk action without approval.

### Cost tests

For each benchmark track:

- completion rate,
- cloud calls/task,
- premium calls/task,
- token/image/audio use,
- local inference latency,
- dollars/task estimate,
- deterministic-skill hit rate.

### Recovery tests

Inject:

- crash,
- window move/dialog,
- selector drift,
- network outage,
- API timeout,
- changed webpage,
- DB unavailable,
- file permission error.

---

## 29. Step-by-step implementation roadmap from current SystemAI V0.2

### Phase 0 - Contracts and architecture - DONE in current baseline

Implemented concepts:

- typed ActionIntent/ActionResult contracts,
- capability definitions,
- task states,
- policy decisions,
- verification contracts.

Acceptance: unit tests pass.

### Phase 1 - Trusted Core - DONE in current baseline

- DAG/cycle/dependency engine.
- Runtime lifecycle.
- Policy Kernel.
- HMAC short-lived capability token mechanism.
- Execution Gateway abstraction.
- verifier/recovery foundations.
- SQLite memory/audit foundation.
- prompt trust boundary/redaction.

Current local suite: 17 passing tests as of the blueprint generation run.

### Phase 2 - macOS Desktop Adapter - CODED/MOCK-TESTED, REAL MAC VALIDATION REQUIRED

- Cua CLI/driver adapter.
- semantic app/window/element resolution.
- fresh observations/tokens.
- desktop verification.
- permission/readiness doctor.

Required before marking production-ready:

- run signed/stable CuaDriver.app on macOS,
- grant Accessibility + Screen Recording,
- execute benchmark workflows on actual Finder/TextEdit/Calculator/Chrome,
- validate background actions/focus and failure cases.

### Phase 2.5 - Cost Intelligence - NEXT CRITICAL FOUNDATION

Implement:

- ModelRouter,
- CostController,
- ConfidenceEngine,
- LocalModelProvider abstraction,
- OpenAI-compatible provider interface,
- dynamic tool catalog,
- context compressor,
- model-call ledger,
- task budgets,
- deterministic/skill-first route.

Acceptance:

- simple commands trigger zero remote calls,
- task budget prevents extra escalation,
- provider fallback tested,
- model/cost dashboard reports usage.

### Phase 3 - Local perception and vision recovery

- compact UI normalization,
- screenshot hash/diff/crop,
- OCR/local CV,
- local grounding/VLM adapter,
- optional OmniParser-like parser,
- before/after visual reflection,
- vision output -> typed intent only.

Acceptance:

- recover from inaccessible/custom canvas controls in a test app,
- no cloud vision on unchanged frames,
- ambiguous visual target fails safely.

### Phase 4 - Production browser hybrid

- Playwright/CDP session manager,
- logged-in profile option,
- deterministic selectors/actions,
- download/upload manager,
- site skill registry,
- generated helper sandbox,
- cached/self-healing browser workflows.

Acceptance:

- BrowserGym workflows,
- repeated workflow runs with no model call after skill is cached,
- drift invokes repair only for affected step.

### Phase 5 - System observation and World State

- filesystem watchers,
- process/service collectors,
- port/network collectors,
- resource health,
- window/app events,
- persistent resource identities,
- world state projection.

Acceptance:

- idle system makes zero LLM calls,
- events update world state,
- known event rule triggers deterministic action.

### Phase 6 - Diagnosis Engine

- hypotheses/tests/evidence objects,
- root-cause ranking,
- technical diagnostics library,
- remediation generation,
- minimal-change planner,
- before/after health verifier.

Acceptance:

- scripted failures: occupied port, dead service, missing env, unavailable DB, disk threshold,
- correct cause isolated and verified.

### Phase 7 - Persistent Capability Graph, Memory and Skill Compiler

- graph DB tables,
- local embeddings/sqlite-vec,
- semantic retrieval,
- trajectory summarization,
- skill candidate compiler,
- regression replay/qualification,
- versioned skill registry.

Acceptance:

- repeated successful task compiles into a skill,
- skill replays with zero cloud calls,
- environment drift invalidates or repairs skill safely.

### Phase 8 - Voice

- local VAD,
- whisper.cpp/faster-whisper adapter,
- local TTS adapter,
- cloud STT/TTS fallback,
- optional realtime premium voice profile.

Acceptance:

- normal voice command works offline/local,
- low-confidence audio escalates based on policy,
- no recording is retained unless policy says so.

### Phase 9 - Secure Coding Runtime + Privileged Helper

- OpenHands/Codex-inspired sandbox service,
- read-only/workspace-write/network allowlist modes,
- command parser/policy,
- Rust privileged helper,
- OS Keychain secret broker.

Acceptance:

- untrusted project cannot escape workspace sandbox,
- privileged operation requires a valid scoped token/approval,
- model never sees raw OS admin credential.

### Phase 10 - Application discovery and adapter SDK

- app metadata discovery,
- capability probing,
- menu/accessibility exploration,
- custom app adapter/plugin SDK,
- signed skill/app packs.

Acceptance:

- unknown app can be inspected and operated under supervised safe exploration,
- generated capability registration is reviewed/tested before unattended use.

### Phase 11 - Windows and Linux hardening

- validate Cua/alternate driver backend,
- Windows UIA integration edge cases,
- Linux AT-SPI integration,
- OS-specific permission/sandbox behavior,
- platform integration tests.

### Phase 12 - Multi-device / remote

Inspired by UFO Galaxy:

- device registry,
- health/capability profile,
- authenticated encrypted agent protocol,
- DAG node placement,
- device-scoped capability tokens,
- remote observation/verification,
- offline/reconnect behavior.

### Phase 13 - Production hardening

- code signing/notarization/Authenticode,
- secure updater,
- SBOM/dependency scanning,
- pinned dependency SHAs/versions,
- migration/recovery/backup,
- telemetry opt-in and privacy controls,
- crash reporting/redaction,
- enterprise policies,
- benchmark gates in CI,
- penetration testing/threat review.

---

## 30. Current V0.2 implementation gap matrix

Implemented and locally tested:

- core typed contracts,
- task graph,
- runtime/state lifecycle,
- capability registry,
- basic in-memory capability graph,
- policy kernel,
- prompt trust boundary,
- redaction,
- capability tokens,
- execution abstraction,
- local/mock executor,
- browser scaffold,
- Cua adapter/CLI integration code,
- desktop semantic contracts,
- verifier/desktop probe,
- basic recovery engine,
- SQLite memory/audit foundation,
- event bus/process monitor foundation,
- skill registry foundation,
- diagnosis scaffold,
- FastAPI local API,
- React/Tauri shell.

Partial / needs hardening:

- real desktop backend across platforms,
- browser executor,
- recovery intelligence,
- diagnosis,
- memory retrieval,
- system monitoring,
- capability graph persistence.

Not yet implemented in V0.2:

- cost/model router,
- local LLM/VLM runtime integration,
- local STT/TTS,
- screenshot diff/OCR/CV pipeline,
- persistent world model,
- skill compiler,
- demonstration recorder,
- full automation scheduler,
- secret broker,
- privileged Rust helper,
- sandboxed coding service,
- application discovery SDK,
- multi-device layer,
- full benchmark harness,
- installer/signing/updater.

Therefore V0.2 is a working architecture/core baseline, not the completed final autonomous SystemAI product.

---

## 31. Dependency and licensing strategy

Rules:

1. Prefer adapters/dependencies over copied source.
2. Pin exact audited versions/commit SHAs.
3. Record license, purpose, security notes, date audited.
4. Generate SBOM.
5. Isolate copyleft services if used and ensure distribution model complies.
6. Review model-weight licenses separately from code licenses.

Examples from the reviewed ecosystem:

- UFO: permissive MIT reference.
- Cua: permissive MIT reference/dependency.
- Agent-S: Apache-2.0 reference.
- agent-ctrl: Apache-style/permissive reference; verify current release before bundling.
- Agent Desktop/Open Computer Use/Browser Harness/Stagehand: verify exact package/release license during integration.
- Skyvern: AGPL concerns for copied/linked deployment; keep as architecture reference or isolated service unless licensing is intentionally accepted.
- OmniParser: code/model weights may have different terms; review each asset.
- Piper current project uses GPL licensing; treat as optional external service unless product licensing accepts it.

Never assume a GitHub repository's README license summary covers downloaded model weights.

---

## 32. Production definitions of autonomy

SystemAI should expose configurable autonomy modes rather than one dangerous "full access" toggle.

### Observe

Read-only system/app state.

### Assist

Prepare plans/drafts and require approval for mutations.

### Standard Auto

Autonomously execute reversible, scoped low-risk actions; ask for consequential actions.

### Workflow Auto

A reviewed skill/workflow gets pre-authorized capabilities/scopes for unattended execution.

### Maintenance Auto

Approved system-repair skills may execute defined service/process/config remediation within a strict manifest.

### Lab / Unrestricted

Only inside disposable VM/test environments; never the consumer default.

---

## 33. Definition of "complete"

SystemAI should not be called complete merely when it can click applications.

V1 completion gate:

- real macOS daily-use workflows stable,
- Windows and Linux basic execution validated,
- browser/API/desktop hybrid routing,
- deterministic independent verification,
- cost/local model routing,
- local voice,
- event monitoring,
- diagnosis for common system faults,
- memory/skills with replay,
- security kernel + sandbox + privileged helper,
- approval UX,
- audit and cost dashboard,
- OSWorld/BrowserGym/AppWorld-style regression gates,
- signed installers and secure updates,
- documented limitations.

Longer-term V2:

- robust application self-discovery,
- multi-device orchestration,
- enterprise policies/remote administration,
- advanced skill marketplace/pack distribution,
- richer local multimodal models,
- continual improvement from reviewed demonstrations.

---

## 34. Final architectural rule

The project should preserve this path for every consequential action:

**User/Automation -> GoalContract -> Task DAG -> Capability Selection -> typed ActionIntent -> Policy/Approval -> Capability Token -> Trusted Executor -> Fresh Observation -> Independent Verification -> Memory/Audit -> Recovery or Completion.**

And preserve this cost rule for every AI decision:

**Deterministic/Skill -> Small Local -> Local LLM/VLM -> Cheap Specialist API -> Premium Cloud Reasoner.**

Those two invariants are the core of SystemAI.
