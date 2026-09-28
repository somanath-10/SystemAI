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

---

# 35. SystemAI Consolidated Production Architecture V3

**Status:** Current implementation direction and source-of-truth architecture as of 2026-09-28.

**Precedence rule:** Sections 1-34 remain valuable for product intent, historical research, requirements, and design rationale. Where this V3 section conflicts with an earlier implementation sequence, trust-boundary decision, state model, or rollout assumption, **Section 35 takes precedence**.

This revision incorporates the complete architectural review, security critique, updated open-source ecosystem review, cost-control goals, local-first requirements, browser/desktop/coding/monitoring use cases, and the requirement that SystemAI remain model-independent and safe even when the reasoning model is wrong or prompt-injected.

## 35.1 Product definition

SystemAI is a **local-first operating-intelligence layer**, not a mouse-clicking bot and not an unrestricted LLM process. It accepts a user goal or trusted automation trigger, turns the goal into a constrained plan, executes actions through typed and policy-controlled capabilities, observes the resulting state, verifies success independently, recovers from failure, and learns reusable procedures that reduce future model cost.

The product must eventually support:

- desktop/application control;
- browser workflows;
- file and system-resource operations;
- developer-environment diagnosis and repair;
- cross-application workflows;
- event-driven monitoring and automations;
- local and cloud AI routing;
- voice as a later interaction layer;
- reusable skills and workflow compilation;
- optional multi-device execution after single-device reliability is proven;
- strict audit, privacy, security, cost, and evaluation controls.

The first product wedge should be **developer-environment diagnosis and repair on macOS**, because it is highly useful, largely structured, sandboxable, measurable, and independently verifiable.

Example flagship request:

> "Find why this project is not running and fix it."

SystemAI should inspect files, Git state, manifests, dependencies, environment/configuration, processes, ports, services, containers, databases, logs, tests, and health endpoints; form evidence-backed hypotheses; run bounded discriminating tests; apply the smallest permitted fix; restart/retest; and verify the original success condition.

## 35.2 Permanent architectural invariants

### 35.2.1 Authority invariant

Every consequential action must follow this path:

```text
User / Trusted Automation
        -> GoalContract
        -> Validated Task DAG
        -> Capability Selection
        -> Typed ActionIntent
        -> Provenance Evaluation
        -> Trusted Security Kernel
        -> Canonical Risk + Policy
        -> Approval if required
        -> Signed Short-Lived Capability
        -> Trusted Executor
        -> Fresh Observation
        -> Independent Verification
        -> Durable Event/Audit Record
        -> Completion, Recovery, or Replan
```

Never allow:

```text
LLM -> unrestricted root/admin shell -> host
```

or:

```text
LLM -> direct desktop authority without policy/verification
```

The reasoning plane may be mistaken, compromised by prompt injection, or simply uncertain. The execution plane must remain bounded even under those conditions.

### 35.2.2 Cost/intelligence invariant

The preferred decision ladder is:

```text
Deterministic operation
    -> Qualified cached skill
    -> Tiny/local classifier or parser
    -> Local LLM/VLM where benchmarked reliable
    -> Inexpensive specialist/cloud model
    -> Premium frontier reasoner only when justified
```

However, optimization must come **after** establishing a strong planner baseline. Do not build a cost router before a real planner and evaluation harness exist.

### 35.2.3 Structured-first execution invariant

The permanent action preference is:

```text
1. Official service/application API
2. MCP / connector / integration
3. Native OS/application API
4. Browser DOM / CDP / Playwright
5. Accessibility API
6. Known keyboard shortcut
7. Local vision / grounding
8. Raw coordinates / pointer fallback
```

Vision and raw coordinates are recovery mechanisms, not the default interface.

### 35.2.4 Fresh-target invariant

The planner expresses **semantic intent**, not long-lived native handles. Executors must resolve the current process/window/page/element immediately before acting. Snapshot-scoped references expire when the underlying UI changes.

### 35.2.5 Verification invariant

"The tool returned success" is never the final success condition. SystemAI verifies requested effects through fresh system state, preferably through an independent mechanism.

### 35.2.6 Fail-closed invariant

If a target is missing, ambiguous, stale, outside policy, unverifiable, or requires authority SystemAI does not possess, do not guess. Re-observe, re-resolve, re-plan, request approval, or stop safely.

## 35.3 Final process architecture

SystemAI should be split into clear trust domains rather than placing authority, planning, and execution in one Python process.

```text
USER / EVENT / AUTOMATION
          |
          v
+-------------------------------+
| Tauri Command Center          |
| React + TypeScript            |
| UI, status, approvals, audit  |
+---------------+---------------+
                | narrow IPC
                v
+================================================+
| TRUSTED RUST SECURITY KERNEL                  |
|                                                |
| schema validation                              |
| canonical risk                                 |
| provenance / taint enforcement                 |
| policy                                         |
| scope checks                                   |
| approval verification                          |
| capability signing                             |
| secret authorization                           |
| security audit                                 |
+================+===============================+
                 | signed capability
                 v
+----------------+-------------------------------+
| Python Orchestrator                            |
|                                                |
| Goal Interpreter                               |
| single Planner                                 |
| Task DAG                                       |
| Scheduler                                      |
| Resource Lease Manager                         |
| Context Builder                                |
| Model Router (later)                           |
| Recovery / Diagnosis                           |
| Memory / Skills                                |
+----------------+-------------------------------+
                 | typed calls
                 v
+----------------+-------------------------------+
| Execution Gateway                              |
| API/MCP | Browser | Desktop | Files | Process |
| Services | Network | Database | Sandbox       |
+--------+-------------+----------------+---------+
         |             |                |
         v             v                v
      Cua/AX       Playwright/CDP     OS APIs
         |             |                |
         +-------------+----------------+
                       |
                       v
                REAL SYSTEM STATE
                       |
                       v
                OBSERVATION PLANE
                       |
                       v
                INDEPENDENT VERIFIER
                       |
          +------------+------------+
          |                         |
       success                    failure
          |                         |
          v                         v
   Event Log / Audit        Recovery / Replan
   Memory / Skill Eval      Alternate Executor
```

Two additional special-purpose processes are required:

1. **Sandboxed coding worker** for project code/shell operations.
2. **Privileged helper** implemented as a very narrow Rust service for explicitly approved elevated operations.

The privileged helper must never receive natural-language prompts or arbitrary shell text.

## 35.4 Trusted Security Kernel

The Security Kernel is the root of execution authority. It must be independent of the model runtime and should be implemented in Rust.

It owns:

- ActionIntent schema validation;
- capability-registry lookup;
- canonical risk classification;
- canonical reversibility classification;
- provenance/taint enforcement;
- resource-scope validation;
- user/session policy;
- approval requirements;
- approval-state verification;
- capability-token creation/signing;
- secret-broker authorization;
- high-integrity audit events;
- replay/nonce protection.

Python may request authority. Python does not own authority.

### 35.4.1 Planner risk fields are advisory only

The planner may output:

```text
risk_hint
expected_reversibility
proposed_executor
```

The kernel independently derives:

```text
canonical_risk
canonical_reversibility
required_approval
required_isolation
allowed_scope
```

The model can never lower the kernel's risk decision.

## 35.5 Capability-token architecture

For cross-process trust boundaries, prefer **asymmetric signatures** instead of sharing one HMAC secret across the kernel and executors.

Recommended structure:

```text
Security Kernel
  private signing key
        |
        v
Signed Capability
        |
        v
Executor
  public verification key only
```

A token should bind at least:

```text
capability_id
session_id
task_id
node_id
action_hash
capability_name
resource_scope
parameter_hash
approval_id when required
provenance constraints
issued_at
expires_at
nonce
```

Executors may verify capabilities but must not mint new capabilities.

For a single-process prototype, the existing HMAC mechanism can remain temporarily, but it must not be considered the final production trust boundary.

## 35.6 Local IPC architecture

Do not treat an ordinary localhost HTTP port as the main production security boundary for a system with desktop/file/process authority.

Preferred production communication:

### macOS/Linux

```text
Unix domain socket
+ filesystem permissions
+ peer/process identity where available
+ ephemeral session authentication
```

### Windows

```text
Named pipe
+ Windows ACL
+ process/session identity
+ ephemeral session authentication
```

FastAPI may remain for development, diagnostics, or an explicitly enabled debug API, but must use strong authentication and strict Host/Origin/CSRF controls when enabled.

## 35.7 GoalContract

Every user request becomes an immutable or tightly controlled GoalContract before planning.

Required fields:

```text
objective
constraints
success_conditions[]
forbidden_effects[]
expected_artifacts[]
resource_scope[]
approval_policy
deadline / priority
privacy profile
budget profile
```

The planner may refine a plan but may not silently redefine the user's objective, forbidden effects, or authority scope.

## 35.8 Planner architecture

V1 should use **one strong planner**, not a swarm of reasoning agents.

The planner receives only:

- the GoalContract;
- currently relevant capabilities;
- current relevant world state;
- top relevant memory/skills;
- recent failures/effects;
- an intentionally small tool catalog.

The planner outputs structured data only:

- task DAG creation/modification;
- semantic ActionIntent proposals;
- clarification requests when genuinely required;
- recovery/replan proposals.

Do not begin V1 with Supervisor LLM + Browser Agent LLM + Coding Agent LLM + Desktop Agent LLM + Verifier LLM. Specialized tools are enough initially. Additional reasoning agents should be introduced only when evaluation proves a measurable benefit.

## 35.9 Task DAG

Every complex task is represented as a durable DAG rather than an opaque loop.

Each node contains:

```text
node_id
objective
dependencies[]
required_capabilities[]
input_bindings
output_bindings
expected_postconditions[]
forbidden_effects[]
resource_requirements[]
risk_hint
retry_policy
recovery_policy
time_budget
cost_budget
preferred_executor
state
```

Core states:

```text
CREATED
READY
WAITING_FOR_RESOURCE
WAITING_FOR_APPROVAL
RUNNING
VERIFYING
COMPLETED
RECOVERING
REPLANNING
FAILED
CANCELLING
CANCELLED
PAUSED
USER_TAKEOVER
```

Graph updates must be validated for cycles, authorization, and scope before adoption.

## 35.10 Resource Lease Manager

Logical DAG parallelism does not imply safe desktop parallelism.

SystemAI must explicitly lock scarce resources such as:

```text
desktop.focus
desktop.keyboard
desktop.pointer
app:<bundle-or-process-id>
window:<stable-runtime-id>
browser-profile:<profile>
filesystem:<scope>
service:<name>
port:<number>
database:<scope>
```

Two tasks requiring `desktop.focus` cannot execute concurrently. Independent API calls, file hashing, or database reads may run in parallel when scopes do not conflict.

## 35.11 Provenance and taint tracking

Source trust classification alone is not enough. Data must carry provenance through transformations.

Trust classes include:

### Trusted authority sources

- authenticated user instructions;
- administrator/system policy;
- capability definitions;
- qualified and reviewed signed skills.

### Untrusted observation sources

- web pages;
- emails;
- documents/PDFs;
- terminal output;
- downloaded files;
- application UI text;
- clipboard data;
- external messages;
- repository/project contents not explicitly trusted as instructions.

Represent important values as provenance-carrying objects:

```text
Value {
  data,
  trust_class,
  source_type,
  source_resource,
  sensitivity,
  derived_from[],
  transformation_history[]
}
```

Example: if an email recipient came from a webpage, the policy layer must still know that when the value later reaches `SendEmail.recipient`.

Untrusted content never becomes higher-authority instruction merely because an LLM summarized or transformed it.

## 35.12 Approval architecture

Approval is a security control, not just UI.

The approval screen must be rendered from the kernel's canonical typed action, not the model's natural-language summary.

Example:

```text
Capability: filesystem.delete
Target: 4 files under ~/Project/build/
Method: Move to Trash
Reversible: Yes
Task: task_182 / node_14
Reason: Clean build artifacts
```

The desktop executor must be unable to automate:

- SystemAI approval windows;
- SystemAI security/permission pages;
- Touch ID / Windows Hello / OS-auth prompts;
- password-manager/credential prompts;
- UAC/security surfaces;
- privacy permission panes.

High-impact approvals should use an independent user-presence mechanism where practical.

## 35.13 Kill switch, pause, and human takeover

The product must always expose:

```text
PAUSE
STOP
TAKE CONTROL
```

If real user keyboard/mouse interaction is detected during GUI automation, the agent should normally relinquish its desktop lease and enter `USER_TAKEOVER` or `PAUSED` state instead of fighting the user for focus.

Rate limits and emergency stop behavior must be enforced outside the model.

## 35.14 Secret Broker

The model should normally see only a secret reference, never a raw password/token.

A credential record must be origin- and usage-bound:

```text
credential_id
type
allowed_origins[]
allowed_applications[]
allowed_usage[]
prohibited_usage[]
sensitivity
rotation metadata
```

Example:

```text
credential_id: github_main
allowed_origins:
  - https://github.com
  - https://api.github.com
allowed_usage:
  - LOGIN_FORM
  - API_AUTH
prohibited_usage:
  - CLIPBOARD
  - MODEL_CONTEXT
  - LOGS
```

Secret storage should use the platform-native secure store:

- macOS Keychain;
- Windows Credential Manager / DPAPI/CNG as appropriate;
- Linux Secret Service/keyring.

The broker refuses secret use on a mismatched origin even if the model asks for it.

## 35.15 Execution Gateway

All runtime side effects pass through one typed gateway.

Executor families:

```text
ApiExecutor
McpExecutor
BrowserExecutor
ComputerExecutor
FileExecutor
ProcessExecutor
ServiceExecutor
NetworkExecutor
DatabaseExecutor
SandboxExecutor
PrivilegedExecutor
```

Each capability definition should include:

```text
idempotent
retry_safe
supports_idempotency_key
reversible
compensation_strategy
risk_class
required_permissions
supported_verifiers[]
resource_scope_model
```

## 35.16 Desktop execution

Define one stable `ComputerExecutor` contract independent of a specific backend.

Typical methods:

```text
list_apps
list_windows
observe_app
observe_window
launch
activate
close
find_elements
invoke
click
set_value
type_text
press
scroll
drag
screenshot
wait_for
```

### Initial primary backend: Cua

Use Cua behind a `CuaExecutor` adapter because its architecture aligns with several SystemAI requirements:

- native driver separated from the model runtime;
- stable macOS driver identity for permissions;
- bounded capability modes/manifests;
- cross-platform abstraction;
- explicit app/window targets;
- doctor/readiness checks.

SystemAI's own policy kernel remains authoritative; Cua is an execution backend, not SystemAI's global security model.

### Optional/secondary backends and references

- **agent-ctrl**: useful snapshot-scoped references, ARIA-like accessibility normalization, fresh resolution, mock surfaces; keep optional while it matures.
- **Open Computer Use**: useful compact semantic accessibility tools and local/background-first ideas.
- **Agent Desktop**: useful native/Rust accessibility normalization reference.
- **agent-computer-use**: useful newer accessibility-first Rust implementation reference.
- **macOS Harness**: useful source of Mac interaction primitives, but its broad-agent-authority philosophy should not replace SystemAI policy boundaries.
- platform-native fallbacks may be added where a backend is insufficient.

## 35.17 Browser execution

The default browser automation environment must use a **dedicated SystemAI browser profile**, not the user's normal personal profile.

Default profile properties:

```text
separate user-data directory
isolated cookies/session state
controlled extensions
controlled downloads/uploads
domain allowlist support
origin-aware Secret Broker
browser-session audit
```

Attaching to a user's personal logged-in profile should be an explicit, scoped, time-limited option with stronger approval policy.

Preferred browser path:

```text
API / MCP
 -> Playwright / CDP
 -> qualified deterministic helper
 -> AI-assisted DOM action
 -> browser accessibility
 -> local visual grounding
 -> cloud computer-use fallback
```

### Stagehand pattern to adopt

Use a lifecycle similar to:

```text
AI exploration
 -> successful trace
 -> deterministic cached helper
 -> regression test
 -> inference-free normal replay
 -> detect drift
 -> repair only the affected step
```

### Browser Harness / BrowserCode pattern to adapt safely

Agents may generate reusable helpers, but generated code must be treated as untrusted code:

```text
Generated helper
 -> static checks
 -> sandbox
 -> restricted browser capability
 -> regression test
 -> qualification
```

Never dynamically load arbitrary agent-generated browser code into the same privileged host process.

## 35.18 Coding and shell runtime

This is central to the first product wedge.

Default execution must occur in a separate sandbox.

Profiles:

```text
READ_ONLY
WORKSPACE_WRITE_NO_NETWORK
WORKSPACE_WRITE_ALLOWLIST_NETWORK
TEMPORARY_CONTAINER_OR_VM
APPROVED_ELEVATED_HOST_OPERATION
```

Generic unrestricted host shell is not a normal SystemAI capability.

Compound shell commands may be parsed as a UX aid, but the real security boundary must be OS/container/sandbox enforcement, not command-string parsing.

Useful architecture references:

- OpenHands: Action/Observation/EventStream and runtime separation;
- Open Interpreter / Codex-like patterns: sandbox policy separate from approval policy;
- OpenClaw-style host gateway + sandboxed risky execution.

Do not copy agent patterns that execute arbitrary model-generated Python directly on the host.

## 35.19 Privileged Helper

The privileged helper is a narrow Rust process/service.

It receives only:

```text
operation identifier
typed validated parameters
signed capability token
approved scope
expiration
nonce
```

It does not receive prompts, webpage text, model output, or arbitrary shell commands.

Examples of acceptable privileged operations may include narrowly defined service-management or package-management actions where the operation and allowed arguments are explicitly modeled.

## 35.20 Perception and visual recovery

The visual pipeline should be escalation-based:

```text
DOM / Accessibility
       |
       v if insufficient
Targeted screenshot
       |
       v
Perceptual hash / changed-region detection
       |
       v
OCR / local CV
       |
       v
OmniParser-like candidate detection
       |
       v
Local VLM grounding
       |
       v
Cloud vision/computer-use fallback
```

Do not repeatedly send full desktop screenshots to a VLM when nothing changed.

Perception output is **never execution authority**. It produces candidate observations/targets that still pass through typed ActionIntent and the Security Kernel.

## 35.21 Observation model

Every observation should carry:

```text
observation_id
source_type
source_resource
timestamp
freshness/generation
trust_class
sensitivity
content_hash
structured_data
artifact_reference
redactions[]
provenance
```

Observation sources include:

- accessibility trees;
- browser DOM/CDP;
- screenshots/crops;
- OCR/CV/VLM results;
- files;
- filesystem watchers;
- processes/services;
- ports/network state;
- system health;
- database/API results;
- sandbox output;
- application events.

Password field contents must never be included in ordinary observations.

## 35.22 Event-sourced system state

The durable **append-only event log** should be the primary runtime source of truth.

Examples:

```text
GoalCreated
PlanCreated
TaskNodeReady
ResourceLeaseGranted
ActionPrepared
PolicyDenied
ApprovalRequested
ApprovalGranted
CapabilityIssued
ActionDispatchStarted
ActionDispatched
ObservationReceived
VerificationPassed
VerificationFailed
RecoveryStarted
TaskCompleted
TaskFailed
```

Build projections from the event log:

```text
TaskProjection
WorldStateProjection
ApplicationProjection
CapabilityProjection
SkillProjection
CostProjection
AuditProjection
```

This reduces inconsistency across Capability Registry, Capability Graph, World State, Application Registry, Task State, and Memory.

SQLite with WAL mode is sufficient initially. Add more infrastructure only after measured need.

## 35.23 Crash-safe execution and action journal

SystemAI must survive crashes around external side effects.

Use a write-ahead action journal:

```text
PREPARED
 -> AUTHORIZED
 -> DISPATCHING
 -> DISPATCHED
 -> EFFECT_OBSERVED
 -> VERIFIED
```

If SystemAI crashes after `DISPATCHED` but before `VERIFIED`, recovery enters:

```text
COMMIT_STATUS_UNKNOWN
```

It must inspect external state before deciding whether to retry.

This is essential for:

- sending email;
- submitting forms;
- creating tickets;
- deployments;
- deleting/moving objects;
- database writes;
- financial or account mutations.

Use native idempotency keys whenever the underlying API supports them.

## 35.24 Reversibility and undo

`reversible=true` is valid only when an actual recovery mechanism exists.

Examples:

```text
Delete file      -> move to Trash/recycle bin first
Overwrite file   -> backup/version first
Code edit        -> Git/checkpoint snapshot
Config change    -> record previous value
Database update  -> transaction/compensating operation
Email            -> draft before send when appropriate
Package update   -> record previous version
Service change   -> record previous state
```

The kernel derives reversibility from capability metadata and operation semantics, not from the planner's confidence.

## 35.25 Verification architecture

Verification has three levels.

### Hard verification

Deterministic checks such as:

```text
file exists
hash matches
process alive
port listening
HTTP health returns expected response
database state matches
git diff matches intended change
DOM/accessibility value matches
```

### Independent secondary verification

Where possible, verify through a mechanism different from the executor.

Example:

```text
Desktop click Save
 -> verify filesystem timestamp/hash/content
```

rather than trusting the desktop executor's success return.

### Semantic or human verification

Use for inherently subjective goals such as "looks professional" or "message is appropriate". Such outcomes may require a local/cloud semantic verifier or human review and must not be represented as deterministic certainty.

### Collateral-damage checks

Each node declares both:

```text
expected_effects[]
forbidden_effects[]
```

Compare start/end state only within a bounded `CollateralScope`, such as:

- declared project directories;
- target process group;
- target application;
- target browser profile;
- declared DB tables;
- target account/service.

Do not attempt an unbounded whole-desktop diff for every action.

## 35.26 Recovery engine

Classify failure before retrying.

Recommended classes:

```text
STALE_REFERENCE
TARGET_NOT_FOUND
AMBIGUOUS_TARGET
PERMISSION_DENIED
RESOURCE_BUSY
NO_EFFECT
POSTCONDITION_FAILED
TIMEOUT
NETWORK_FAILURE
PAGE_CHANGED
APP_CHANGED
DEPENDENCY_FAILURE
SANDBOX_DENIED
BUDGET_EXHAUSTED
COMMIT_STATUS_UNKNOWN
```

Recovery ladder:

```text
Re-observe
 -> Re-resolve target
 -> Safe/idempotent retry
 -> Alternative structured executor
 -> Qualified skill alternative
 -> Local visual grounding
 -> Diagnosis
 -> Re-plan only affected DAG branch
 -> Cloud escalation if justified
 -> Human decision when necessary
```

Never infinite-loop.

## 35.27 Diagnosis engine

Diagnosis is evidence-driven, not one-shot model guessing.

Represent hypotheses explicitly:

```text
Hypothesis {
  cause,
  supporting_evidence[],
  contradicting_evidence[],
  discriminating_test,
  test_cost,
  test_risk,
  confidence_evidence,
  status
}
```

Workflow:

```text
symptom
 -> hypotheses
 -> rank by evidence/prior/context
 -> cheapest safe discriminating tests
 -> update evidence
 -> isolate cause
 -> minimal remediation plan
 -> policy/approval
 -> apply fix
 -> restart/retest
 -> verify original success condition
 -> store trajectory as candidate repair skill
```

The diagnosis engine never bypasses policy because it is "repairing" the machine.

## 35.28 Developer diagnosis V1 workflow

For `Find why this project is not running and fix it`:

```text
1. Discover project/runtime.
2. Inspect source tree and Git state.
3. Read package/build manifests and lock files.
4. Inspect recent logs and stack traces.
5. Inspect expected process.
6. Inspect expected/listening ports.
7. Inspect required DB/services/containers.
8. Inspect environment/configuration presence and shape.
9. Inspect dependency versions/install state.
10. Inspect recent Git changes.
11. Build ranked hypotheses.
12. Run low-risk discriminating tests.
13. Generate the minimum-scope fix.
14. Snapshot/backup modified state.
15. Request approval if required.
16. Apply fix through sandbox/typed executor.
17. Restart relevant component only.
18. Run tests.
19. Run health checks.
20. Verify the user's original success condition.
21. Report exact changes and unresolved limitations.
22. Store the trajectory as a candidate skill, not automatically trusted automation.
```

## 35.29 Confidence and escalation

Do not use self-reported LLM confidence as the primary control signal.

Use evidence such as:

```text
schema_valid
task_class_known
skill_match_strength
target_uniqueness
executor_reliability
postcondition_strength
historical_success_rate
planner self-consistency
failure_count
state novelty
verification agreement
risk class
```

The first ConfidenceEngine may be a deterministic scoring/rule system calibrated from real runs.

## 35.30 Model Router and Cost Controller

Build these only after baseline planner/eval measurements exist.

Router inputs:

```text
task class
complexity
modality
privacy policy
risk
hardware capability
historical success
current failures
latency requirement
remaining budget
```

Outputs:

```text
provider
model profile
reasoning effort
context/tool subset
fallback path
```

Per-task budgets:

```text
max cloud spend
max cloud calls
max premium calls
max image calls
max audio seconds
token/context limits
time/latency limits
```

Track actual/estimated:

```text
provider/model
input/output/cached tokens
image/audio usage
local inference time
CPU/GPU time when measurable
cloud cost
```

## 35.31 Local AI strategy

Do not assume small local models can reliably perform complex planning or GUI grounding on every consumer machine.

Define hardware profiles, for example:

```text
8 GB
16 GB
32 GB
64 GB+
NVIDIA workstation/server
```

Benchmark task classes independently:

- classification;
- routing;
- extraction;
- log summarization;
- structured planning;
- code diagnosis;
- UI grounding;
- screenshot understanding.

Route a task class locally only after its measured success/cost/latency meets the configured threshold.

Provider adapters should remain swappable across local and remote runtimes.

## 35.32 Dynamic tool loading and context compression

Do not expose every capability to every model call.

Examples:

```text
Browser task -> browser/API subset
Backend diagnosis -> files/process/ports/logs/sandbox subset
Document task -> file/document subset
```

Model context should contain only:

```text
GoalContract
current relevant DAG nodes
compact relevant world state
top relevant memory/skills
recent failures/effects
currently permitted tools
```

Do not replay entire histories, logs, or screenshot sequences by default.

## 35.33 Skill architecture

Skills are a major SystemAI differentiator and cost cache, but also a persistence attack surface.

A successful trajectory is **not automatically a trusted skill**.

Qualification lifecycle:

```text
CANDIDATE
 -> PROVENANCE / TAINT ANALYSIS
 -> GENERALIZATION
 -> PARAMETERIZATION
 -> STATIC CAPABILITY ANALYSIS
 -> SANDBOX REPLAY
 -> REGRESSION TESTS
 -> POLICY REVIEW
 -> HUMAN REVIEW when untrusted/high-risk provenance requires it
 -> QUALIFIED
 -> SIGNED
```

Skill schema should include:

```text
id
name
version
purpose
parameters
preconditions[]
steps/sub-DAG
required_capabilities[]
resource_templates[]
provenance_constraints
risk profile
postconditions[]
forbidden_effects[]
rollback strategy
recovery alternatives
environment constraints
supported app/site versions
test suite
qualification result
review identity
signature
```

Skills learned from workflows that touched untrusted content cannot become unattended pre-authorized automation merely because the run completed successfully.

## 35.34 OpenAdapt-style workflow compilation

Adopt the strongest ideas from OpenAdapt/OpenAdapt Flow:

```text
record -> review -> compile -> parameterize -> qualify/certify -> replay/run
```

Cross-workflow handoffs should pass values derived from **verified predecessor effects**. If the expected evidence is missing, halt rather than allowing downstream nodes to assume success.

The Demonstration Recorder remains later-phase, opt-in, local-first, and review/redaction-first.

## 35.35 Cross-application workflow example

User:

> "Take yesterday's sales data, build the report, export PDF and send it to X."

Preferred DAG:

```text
Resolve date
 -> Locate source data
 -> Validate source
 -> Parse spreadsheet directly
 -> Calculate metrics programmatically
 -> Generate chart/report programmatically
 -> Use office GUI only if fidelity/template constraints require it
 -> Export PDF
 -> Verify PDF fields/artifact
 -> Prepare email draft via API/plugin if possible
 -> Verify recipient/body/attachment
 -> Request send approval according to policy
 -> Send
 -> Verify sent state
```

Do not use GUI merely because a human would use GUI.

## 35.36 Monitoring and automations

SystemAI is event-driven, not continuously LLM-driven.

```text
OS/app event
 -> normalize
 -> dedupe/filter
 -> deterministic rule
 -> known automation/qualified skill
 -> local anomaly classifier
 -> AI only if unresolved
```

Useful events:

- process/service lifecycle;
- file changes;
- downloads;
- disk capacity;
- CPU/RAM thresholds;
- ports/network changes;
- app/window lifecycle;
- permission changes;
- device connect/disconnect;
- task/workflow state.

Automations are durable objects containing:

```text
trigger
condition
scope
allowed capabilities
approval policy
budget
cooldown/dedupe
action workflow
audit policy
```

macOS advanced Endpoint Security-based monitoring should be an optional entitlement-dependent enterprise capability. Basic builds should use normal APIs/watchers/polling where appropriate.

## 35.37 Memory architecture

Keep four logical memory types:

```text
Working memory
Episodic memory
Semantic memory
Procedural memory
```

But treat them as durable records/projections over task/event history rather than independent competing truth stores.

- Working: current task state and recent relevant observations.
- Episodic: task outcomes, failures, summaries.
- Semantic: stable approved facts such as project paths/application metadata.
- Procedural: qualified skills and repair procedures.

Retrieve only a small relevant subset into the model context.

## 35.38 Privacy defaults

Default settings should be conservative:

```text
continuous screen recording: OFF
raw screenshot retention: OFF or short/ephemeral
trajectory screenshot retention: minimal/local
clipboard retention: none by default
secret retention in logs: forbidden
telemetry: opt-in
cloud egress: policy controlled
raw demonstration recording: local + explicit user review
```

## 35.39 Audit and observability

Every significant action should record:

```text
event_id
timestamp
actor/session
goal/task/node
action intent
provenance
policy decision
canonical risk
approval identity/time
capability token id
executor/backend
target resource
result/effect
verification evidence
rollback/compensation
recovery/escalation
model/provider
usage/cost
latency
redactions
```

Use append-only/hash-chained audit records initially. Add stronger signing/attestation only when enterprise deployment requires it.

OpenTelemetry-style traces should correlate:

```text
input -> goal -> plan -> policy -> executor -> observation -> verifier -> recovery/memory
```

## 35.40 Cross-platform strategy

SystemAI Core contracts can be platform-neutral. The implementation details cannot.

### macOS

Expect platform-specific components for:

```text
Accessibility (AX)
ScreenCapture
TCC permission identity
Apple Events
Keychain
launchd/service behavior
input injection/background interaction
optional Endpoint Security
```

### Windows

Expect:

```text
UI Automation
Win32
UIPI/UAC
Windows Hello/credential systems
Services
Named Pipes
Windows sandbox/elevation behavior
```

### Linux

Expect:

```text
AT-SPI
X11
Wayland / XDG portals
D-Bus
systemd
Secret Service
sandbox/namespace differences
```

Therefore Windows/Linux are not merely "hardening" of the macOS code. They are significant platform-specific implementations behind common contracts.

## 35.41 User autonomy modes

Expose explicit bounded modes:

### Observe

Read-only system/application state.

### Assist

Prepare plans, drafts, or proposed changes; user approves mutations.

### Standard Auto

Autonomously execute reversible, scoped, low-risk actions; ask for consequential actions.

### Workflow Auto

Only qualified/reviewed workflow capabilities are pre-authorized within an explicit scope.

### Maintenance Auto

Only pre-approved system-repair capabilities operate within a strict maintenance manifest.

### Lab

Broad experimentation only inside disposable VM/test environments.

Do not provide a normal consumer "unrestricted full access to my real computer" mode.

## 35.42 Command Center UX

Primary pages:

```text
Assistant
Running Tasks
Task Graph
Approvals
Activity
Applications
Browser Sessions
Skills
Automations
System Health
Memory
Models
Cost
Security
Audit
Settings
```

For each running task always show:

- what SystemAI is doing;
- why it is doing it;
- current resource/target;
- selected executor;
- risk/approval state;
- observed evidence;
- verification state;
- changes made;
- next action;
- pause/stop/take-control controls.

## 35.43 Open-source ecosystem adoption matrix

SystemAI should borrow specific ideas rather than make any one external agent framework its foundation.

### Cua

**Use:** primary initial ComputerExecutor backend; bounded capability manifests; stable macOS driver identity; doctor/readiness; native driver separation.

**Do not use as:** replacement for SystemAI's global policy/security kernel.

### Microsoft UFO/UFO3 Galaxy

**Use:** DAG decomposition, capability-aware assignment, state-machine ideas, future multi-device concepts.

**Do not use as:** V1 foundation or justification for an early multi-agent architecture.

### Agent-S

**Use:** separate reasoning/grounding concepts, visual reflection, bounded screenshot context.

**Reject:** arbitrary model-generated Python/Bash execution on the host.

### agent-ctrl / older Computer Use Protocol

**Use:** compact normalized accessibility schema, snapshot-scoped refs, fresh target resolution, mock surfaces.

**Note:** older Computer Use Protocol is historical/archived reference; agent-ctrl is the newer direction.

### Open Computer Use / Agent Desktop / agent-computer-use

**Use:** accessibility-first semantic action surfaces and native implementation ideas.

**Keep:** behind SystemAI ComputerExecutor + policy contracts.

### Browser Use / Browser Harness / BrowserCode

**Use:** CDP connectivity, reusable helper generation, agent experimentation.

**Change:** generated helper code must run sandboxed and scoped; dedicated browser profile is default.

### Stagehand

**Use strongly:** deterministic cached browser actions, inference-free replay, self-healing only on drift.

### Skyvern

**Use:** browser workflow and AI/CV fallback ideas.

**Caution:** licensing and screenshot-heavy cost patterns; do not make it the SystemAI core.

### OpenHands

**Use strongly:** Action/Observation runtime separation, sandboxed code execution, reproducible environments.

### Open Interpreter / Codex-style runtime patterns

**Use:** separate sandbox policy from approval policy; read-only/workspace-write/elevated distinctions; fail closed if sandbox enforcement is unavailable.

### OpenClaw-like gateway patterns

**Use:** trusted host gateway + risky execution moved into sandbox.

### OpenAdapt / OpenAdapt Flow

**Use strongly:** record/review/compile/qualify/replay workflow lifecycle; verified-effect handoffs.

### OmniParser

**Use:** optional local perception fallback.

**Caution:** code/model asset licenses may differ; review each asset separately.

### UI-TARS / OpenComputer-style local computer use

**Use:** evidence that local multimodal grounding is feasible in some environments.

**Do not use as:** security boundary; benchmark before routing production tasks locally.

### OSWorld / OSWorld V2.x

**Use:** external desktop regression/evaluation, with pinned reproducible releases.

**Do not use as:** substitute for SystemAI-specific macOS and adversarial tests.

### BrowserGym / WebArena / VisualWebArena / WorkArena

**Use:** browser evaluation framework and benchmark suites.

### AppWorld / AppWorld-UL

**Use:** state-based success evaluation, collateral-effect thinking, user-confirmation/clarification evaluation.

### AgentDojo

**Use:** indirect prompt-injection evaluation for tool-using agents.

### DoomArena

**Use:** adversarial/security testing across computer/browser agent environments.

### CaMeL-style research

**Use:** data-flow/control-flow isolation and capability-aware prompt-injection defense concepts.

**Do not use as:** drop-in production security kernel without independent validation.

## 35.44 Dependency and licensing policy

For every dependency/model:

```text
name
source repository
exact version or commit SHA
license
model-weight license if separate
purpose
security review date
known risks
bundled vs external-service status
```

Rules:

- prefer adapters/dependencies over copied source;
- pin exact audited versions/SHAs;
- generate an SBOM;
- review transitive dependencies;
- review code and model-weight licenses separately;
- isolate copyleft services if the intended distribution model requires it;
- never assume a README license summary covers downloaded model assets.

## 35.45 Final repository architecture

Recommended repository structure:

```text
systemai/
|
|-- apps/
|   `-- desktop/
|       |-- src/                       # React UI
|       `-- src-tauri/                 # signed Tauri shell
|
|-- orchestrator/
|   `-- systemai/
|       |-- goals/
|       |-- planner/
|       |-- task_graph/
|       |-- scheduler/
|       |-- resource_leases/
|       |-- context/
|       |-- models/
|       |-- routing/
|       |-- observation/
|       |-- verification/
|       |-- recovery/
|       |-- diagnosis/
|       |-- skills/
|       |-- memory/
|       |-- monitoring/
|       `-- automations/
|
|-- native/
|   |-- security-kernel/
|   |   |-- policy/
|   |   |-- risk/
|   |   |-- provenance/
|   |   |-- approvals/
|   |   |-- tokens/
|   |   |-- secrets/
|   |   `-- audit/
|   |-- privileged-helper/
|   `-- collectors/
|       |-- macos/
|       |-- windows/
|       `-- linux/
|
|-- executors/
|   |-- gateway/
|   |-- api/
|   |-- browser/
|   |-- desktop/
|   |-- filesystem/
|   |-- processes/
|   |-- services/
|   |-- network/
|   `-- databases/
|
|-- drivers/
|   |-- cua/
|   |-- agent_ctrl/
|   `-- mock/
|
|-- sandbox/
|   |-- runtime/
|   |-- profiles/
|   `-- images/
|
|-- contracts/
|   |-- goal/
|   |-- actions/
|   |-- observations/
|   |-- verification/
|   |-- events/
|   `-- capabilities/
|
|-- storage/
|   |-- migrations/
|   |-- event_store/
|   |-- projections/
|   `-- artifacts/
|
|-- evals/
|   |-- systemai/
|   |-- security/
|   |-- desktop/
|   |-- browser/
|   |-- diagnosis/
|   `-- cost/
|
|-- tests/
|
|-- config/
|   |-- policies/
|   |-- risk/
|   |-- capabilities/
|   |-- models/
|   `-- platforms/
|
|-- docs/
|   |-- architecture/
|   |-- threat-model/
|   |-- security/
|   |-- adapters/
|   `-- runbooks/
|
`-- scripts/
```

## 35.46 Initial persistence model

Start with a compact schema rather than dozens of overlapping state stores:

```text
events
tasks
task_nodes
task_edges
action_journal
observations
verification_results
approvals
capability_metadata
skills
skill_versions
skill_tests
memory_items
model_calls
artifacts
projection_checkpoints
```

Use SQLite + WAL. Use sqlite-vec only when semantic retrieval becomes necessary. Use object/file storage for larger redacted artifacts.

Add PostgreSQL, Qdrant, Redis, Kafka, or a graph database only when measured scale/concurrency requirements justify them.

## 35.47 Evaluation is Phase 0

The evaluation harness must precede major feature expansion.

Create a SystemAI-specific suite of approximately 40-60 initial tasks covering:

```text
files
Git
processes
ports
services
databases
browser
desktop
cross-app workflows
approval
recovery
crash handling
prompt injection
secret handling
skill poisoning
```

Each task should support repeatable setup/reset and state-based verification.

### Core metrics

Track:

```text
Task Success Rate
Verified Task Success Rate
Unsafe Action Rate
Unauthorized Action Rate
Collateral Damage Rate
Human Interventions / Task
Recovery Success Rate
Mean Steps / Task
Model Calls / Task
Premium Calls / Task
Tokens / Task
Images / Task
Cost / Task
p50 Latency
p95 Latency
Skill Hit Rate
Skill Drift Failure Rate
False Approval Rate
Prompt Injection Attack Success Rate
```

### External benchmarks

Use, where applicable:

- pinned OSWorld/OSWorld V2.x releases for desktop evaluation;
- BrowserGym + WebArena/VisualWebArena/WorkArena for browser evaluation;
- AppWorld/AppWorld-UL for state/effect and confirmation evaluation;
- AgentDojo for prompt-injection evaluation;
- DoomArena for adversarial testing.

External benchmarks do not replace SystemAI's own macOS-first suite.

## 35.48 Security/adversarial test catalog

Continuously test:

```text
web prompt injection
email prompt injection
PDF/document injection
terminal output injection
malicious repository instructions
clipboard injection
downloaded README/instructions
encoded/obfuscated instructions
Unicode/homoglyph attacks
tool-result injection
credential exfiltration
target substitution
approval spoofing
skill poisoning
capability-token replay
origin confusion
path traversal
symlink escape
sandbox escape attempts
manifest-widening attempts
high-risk actions without approval
crash-after-side-effect replay
```

Security tests belong in CI from early development, not only in final penetration testing.

## 35.49 Revised implementation roadmap

This roadmap supersedes the previous phase order where they conflict.

### Phase 0 - Evaluation and threat model

Implement:

- 40-60 fixed SystemAI tasks;
- deterministic reset/setup;
- mock executor;
- state-based verification;
- security/adversarial cases;
- metric collection;
- baseline report format.

**Exit gate:** tasks can be reset, executed, independently verified, collateral effects detected, and cost/latency measured.

### Phase 1 - Trusted contracts

Implement/finalize:

- GoalContract;
- TaskNode/TaskEdge;
- ActionIntent/ActionResult;
- Observation;
- VerificationResult;
- Capability definition;
- Event schema;
- ResourceLease;
- idempotency/reversibility metadata.

**Exit gate:** contracts are versioned and fully covered by unit/property tests.

### Phase 2 - Rust Security Kernel

Implement:

- secure local IPC;
- canonical risk;
- policy;
- provenance/taint rules;
- approval verification;
- asymmetric capability signing;
- nonce/replay protection;
- secret authorization;
- security audit.

**Exit gate:** adversarial tests cannot widen scope, forge capability tokens, self-approve, or exfiltrate secrets through normal action paths.

### Phase 3 - Durable orchestration

Implement:

- event store;
- Task DAG;
- scheduler;
- ResourceLeaseManager;
- projections;
- write-ahead action journal;
- crash/recovery checkpoints.

**Exit gate:** forced crashes at every action lifecycle stage recover without duplicate unsafe side effects.

### Phase 4 - Real planner

Implement:

- one strong frontier planner;
- strict structured output;
- DAG generation/modification;
- limited dynamic tool catalog;
- context builder;
- planner evaluation.

**Exit gate:** planner produces valid executable DAGs on the initial eval suite with measurable baseline cost/success.

### Phase 5 - Developer diagnosis vertical slice

Implement production-grade:

- filesystem;
- Git;
- process inspection;
- ports/network;
- logs;
- HTTP health;
- service checks;
- environment/config inspection;
- package manifests/dependencies;
- tests;
- database/container checks where appropriate.

**Exit gate:** the flagship "find why this project is not running and fix it" suite achieves the target verified completion rate with bounded changes.

### Phase 6 - Sandboxed coding runtime

Implement:

- read-only;
- workspace-write;
- network deny;
- network allowlist;
- disposable environment/container;
- snapshots/rollback;
- tool/result redaction.

**Exit gate:** malicious/untrusted projects cannot escape the configured workspace boundary in the test environment.

### Phase 7 - macOS desktop integration

Implement:

- signed/stable driver identity;
- Accessibility/Screen Recording onboarding;
- Cua adapter;
- bounded manifests;
- semantic target resolution;
- fresh accessibility snapshots;
- desktop resource leases;
- takeover detection;
- approval/security-surface exclusions;
- desktop verification.

Real apps:

- Finder;
- TextEdit;
- Calculator;
- Chrome;
- VS Code;
- Terminal where safe.

**Exit gate:** repeatable macOS workflows pass real-device verification, not only mocks.

### Phase 8 - Browser hybrid

Implement:

- dedicated profile;
- Playwright/CDP manager;
- origin policy;
- Secret Broker integration;
- downloads/uploads;
- DOM/accessibility snapshots;
- deterministic selectors/helpers;
- helper sandbox;
- cached skills;
- drift repair.

**Exit gate:** repeated qualified workflows run with zero/low model calls and drift repair affects only the broken step.

### Phase 9 - Perception fallback

Implement:

- targeted screenshots;
- frame hash/diff;
- OCR/CV;
- optional OmniParser-like parser;
- local grounding adapter;
- cloud vision fallback;
- before/after visual reflection where useful.

**Exit gate:** inaccessible/custom controls can be handled in the test environment without turning vision into unrestricted authority.

### Phase 10 - Verification and recovery hardening

Implement:

- reusable capability verifiers;
- bounded collateral scopes;
- failure injection;
- alternative-executor recovery;
- partial-DAG replanning;
- commit-status reconciliation.

**Exit gate:** recovery success is measured and regressions are caught in CI.

### Phase 11 - Cost Intelligence

Only after baseline measurements, implement:

- ModelRouter;
- deterministic ConfidenceEngine;
- CostController;
- hardware profiles;
- local LLM provider;
- local VLM provider;
- context compression;
- model/cost dashboard.

**Exit gate:** routing demonstrates lower cost while preserving configured success/safety thresholds.

### Phase 12 - Skill Compiler

Implement:

- trajectory capture;
- taint/provenance analysis;
- parameterization/generalization;
- static capability analysis;
- sandbox replay;
- regression qualification;
- human review when required;
- signing/versioning;
- drift invalidation/repair.

**Exit gate:** repeated qualified tasks replay reliably with zero or minimal reasoning calls and cannot exceed their approved scope.

### Phase 13 - Monitoring and automations

Implement:

- filesystem watchers;
- process/service monitors;
- ports/network;
- resource health;
- window/app lifecycle;
- durable schedules/conditions;
- cooldown/dedupe;
- rate limits;
- event-to-skill routing.

**Exit gate:** idle system makes zero model calls; known events invoke deterministic rules/skills; AI handles only unresolved exceptions.

### Phase 14 - Production hardening

Implement:

- code signing/notarization/Authenticode as applicable;
- secure updater;
- SBOM;
- dependency/secret scanning;
- pinned dependencies;
- migration/backup/recovery;
- crash reporting/redaction;
- privacy controls;
- support bundle;
- benchmark gates in CI;
- threat review/penetration testing.

### Phase 15 - Windows implementation

Implement Windows-specific:

- UIA/Win32 behavior;
- UIPI/UAC constraints;
- Named Pipes;
- Windows sandbox/elevation model;
- credential integration;
- service/process collectors;
- platform test suite.

### Phase 16 - Linux implementation

Implement Linux-specific:

- AT-SPI;
- X11;
- Wayland/XDG portals;
- D-Bus/systemd;
- Secret Service;
- Linux sandbox behavior;
- platform test suite.

### Phase 17 - Voice

Implement only after core reliability:

- local VAD;
- local STT;
- local TTS;
- cloud fallback;
- privacy/retention policy.

### Phase 18 - Demonstration Recorder

Implement:

```text
record -> review -> redact -> compile -> sandbox replay -> verify -> qualify -> sign
```

No raw demonstration egress without explicit policy.

### Phase 19 - Multi-device / remote

Only after one-device execution is stable:

- device registry;
- capability/health profile;
- authenticated encrypted protocol;
- DAG node placement;
- device-scoped capability tokens;
- remote observation/verification;
- reconnect/offline semantics.

## 35.50 Features explicitly deferred from V1

Do not allow these to block the first useful release:

```text
Neo4j
Kafka
multi-agent swarm
skill marketplace
multi-device orchestration
full Windows/Linux parity
voice assistant
continuous VLM monitoring
full autonomous application discovery
unrestricted elevated maintenance
general root/admin shell
```

They may be revisited after evidence shows they are necessary.

## 35.51 V1 completion definition

SystemAI V1 should be considered complete only when all of the following are true:

```text
macOS-first production path is reliable;
Security Kernel is isolated;
real planner exists;
developer diagnosis is strong;
files/process/Git/network tools are reliable;
sandboxed coding runtime works;
browser hybrid is reliable;
basic desktop automation is reliable;
independent verification exists;
crash-safe action recovery exists;
approval UI cannot be self-operated by the agent;
prompt-injection defenses are continuously tested;
dedicated browser profile is default;
origin-bound Secret Broker works;
skills can be qualified/signed/replayed;
cost and model usage are measured;
kill switch/pause/takeover work;
signed installer/update path exists;
benchmark/security regression suites run in CI;
limitations are documented.
```

Windows/Linux may remain later platform phases; V1 should not pretend they have identical maturity if they do not.

## 35.52 Initial quantitative acceptance targets

Exact thresholds should be tuned from baseline data, but an initial serious target is:

```text
Developer diagnosis suite:
  >= 90% verified completion

Core deterministic file/process/API workflows:
  >= 98% verified completion

Simple deterministic browser workflows:
  >= 95% verified completion

Structured desktop accessibility tasks:
  >= 90% verified completion

Unauthorized consequential actions:
  0

Capability scope escapes:
  0

Raw secret exposure in model/audit logs:
  0

Duplicate external effects after deterministic crash tests:
  0

High-risk actions without required approval:
  0

Qualified skill execution outside declared scope:
  0
```

Broad desktop benchmarks should be tracked separately because general computer-use tasks are substantially more difficult than deterministic capability workflows.

## 35.53 Product differentiation

SystemAI should not position itself primarily as:

> "AI that clicks your computer."

The durable product advantage should be:

> **A model-independent, local-first execution and verification layer that gives AI tightly controlled computer authority, proves what changed, recovers safely, learns qualified reusable procedures, and progressively reduces AI cost.**

The defensible combination is:

```text
Typed capabilities
+ isolated Security Kernel
+ provenance/taint tracking
+ trustworthy approvals
+ origin-bound secrets
+ structured-first execution
+ independent verification
+ crash-safe external effects
+ sandboxed code execution
+ resource-aware DAG orchestration
+ qualified skill compilation
+ local-first measured cost routing
+ unified API/browser/desktop/system execution
```

## 35.54 Final SystemAI rule

Every new feature must fit this chain:

```text
USER / TRUSTED EVENT
        -> GOAL CONTRACT
        -> PLAN
        -> TASK DAG
        -> RESOURCE LEASE
        -> TYPED ACTION INTENT
        -> PROVENANCE
        -> SECURITY KERNEL
        -> CANONICAL RISK
        -> POLICY
        -> APPROVAL WHEN REQUIRED
        -> SIGNED CAPABILITY
        -> TRUSTED EXECUTOR
        -> REAL SYSTEM
        -> FRESH OBSERVATION
        -> INDEPENDENT VERIFICATION
        -> EVENT LOG / AUDIT
        -> MEMORY / SKILL EVALUATION
        -> COMPLETE OR RECOVER
```

If a proposed SystemAI feature cannot fit safely into this chain, it should not be granted consequential host authority.

The permanent cost rule remains:

```text
Deterministic
 -> Qualified Skill
 -> Small/Local Intelligence
 -> Local LLM/VLM when benchmarked reliable
 -> Cheap Specialist API
 -> Premium Frontier Reasoner
```

**These two invariants, plus the isolated Security Kernel and independent verification, are the core of the SystemAI architecture.**
