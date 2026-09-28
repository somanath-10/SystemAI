# SystemAI Architecture

## 1. Architectural goal

SystemAI is not a mouse-clicking chatbot. It is an operating intelligence layer that separates cognition from authority and actuation.

```text
REASONING PLANE
  Supervisor / Planner / Diagnosis / Memory / Capability Graph
                         │
==================== TRUST BOUNDARY ====================
                         │
EXECUTION PLANE
  Schema Validation → Policy → Authorization → Executor → Verifier
                         │
==================== SYSTEM BOUNDARY ===================
                         │
  OS / Applications / Browser / Files / Services / APIs
```

A prompt-injected or mistaken planner therefore still cannot bypass executor policy.

## 2. Reference influences

### Microsoft UFO / Galaxy

Adopted concepts:
- explicit agent responsibilities;
- processor-style separation between observation/reasoning/execution/memory;
- finite state machine lifecycle;
- DAG dependency orchestration and cycle rejection.

SystemAI difference:
- the task graph is independent of any desktop automation framework;
- policy and verification are mandatory execution-plane services, not optional agent behavior.

### Cua

Adopted concepts:
- platform driver abstraction;
- exact target/session identity;
- separate authorization/consent/policy concepts;
- effect/verification semantics rather than naive boolean success;
- OS-specific behavior hidden beneath a stable core interface.

SystemAI difference:
- Cua is treated as one replaceable executor adapter, not as the core runtime.

### Agent-S

Adopted concepts:
- current + previous screenshot context;
- reflection on action outcomes;
- visual grounding as a recovery strategy.

Rejected pattern:
- model-generated code reaching `eval`/`exec` or an unrestricted host Python/shell boundary.

### Open Interpreter

Adopted concepts:
- tool router boundary;
- explicit approval/sandbox profiles;
- lifecycle hooks and pluggable integrations.

SystemAI difference:
- all host actions are normalized into capability-scoped `ActionIntent` objects before execution.

### Agent Desktop

Adopted concepts:
- accessibility first;
- stable semantic element identity;
- ambiguous selectors return an error rather than guessing.

### Open Computer Use

Adopted concepts:
- compact semantic desktop capability surface;
- native host application owns OS privacy/accessibility permissions;
- avoid global input when semantic/background methods exist.

## 3. Runtime path

```text
TaskRequest
  ↓
Planner
  ↓
TaskPlan (JSON Schema validated)
  ↓
TaskGraph.from_nodes()
  ↓
TaskStateMachine READY
  ↓
ready node
  ↓
PolicyKernel.evaluate(ActionIntent)
  ├── deny → fail node
  ├── approval → WAITING_FOR_APPROVAL
  └── allow
        ↓
   optional scoped capability token
        ↓
   ExecutionGateway.resolve(capability)
        ↓
   executor.execute()
        ↓
   Verifier.verify()
        ├── pass → SUCCEEDED
        └── fail/unknown
              ↓
         RecoveryEngine
              ├── retry
              ├── vision fallback
              ├── computer fallback
              └── replan
```

## 4. Data contracts

The key security boundary is the typed action contract:

```text
ActionIntent
  task_id
  capability
  target
  parameters
  expected_result
  verification[]
  risk
  reversible
  requires_elevation
  requires_confirmation
```

A planner cannot add arbitrary executable Python. The capability must be registered and have an executor.

`ActionResult` distinguishes execution status from effect status:

```text
status: completed | failed

effect:
  confirmed
  unverifiable
  suspected_noop
  failed
```

Verification is represented separately so executors do not self-certify important state transitions.

## 5. Capability router priority

Preferred order:

```text
1. Official application/API/connector
2. Browser DOM/CDP
3. Native application automation
4. Accessibility tree
5. Keyboard shortcut
6. Vision-grounded UI interaction
7. Global coordinate input
```

Lower layers should be used only when higher-fidelity semantic control is unavailable.

## 6. System Capability Graph

Planned graph entities:

```text
Device
Application
Window
Process
Service
File
Directory
AccountReference
Capability
Skill
Workflow
Permission
Task
```

Important relations:

```text
HAS_CAPABILITY
CAN_OPEN
CAN_EDIT
CAN_PRODUCE
DEPENDS_ON
RUNS_PROCESS
LISTENS_ON
REQUIRES_PERMISSION
USES_CAPABILITY
PRODUCES
OWNED_BY
```

The initial implementation provides a graph API; persistent graph discovery comes next.

## 7. Event-driven autonomy

The event bus is designed so SystemAI does not continuously spend model tokens inspecting the screen.

Collectors should emit structured events such as:

```text
PROCESS_STARTED
PROCESS_EXITED
APPLICATION_CRASHED
FILE_CREATED
FILE_CHANGED
DOWNLOAD_COMPLETED
PORT_CHANGED
NETWORK_CHANGED
DISK_LOW
PERMISSION_CHANGED
```

Rules/anomaly filters decide whether an event warrants diagnosis or only storage.

## 8. Memory and skill learning

Successful tasks are stored as trajectories. A later skill compiler will generalize repeated successful trajectories into parameterized candidate skills, test them, and only then publish them to the skill registry.

A skill never grants new authority: every step still passes through policy and verification.

## 9. V0.2 semantic desktop execution

V0.2 replaces the generic computer-driver placeholder with a concrete Cua Driver adapter while preserving executor independence.

```text
Planner ActionIntent
   │
   │ semantic target only
   ▼
CuaDesktopExecutor
   │
   ├─ resolve application by bundle/name
   ├─ resolve exactly one current window
   ├─ get fresh window state
   ├─ resolve exactly one semantic AX element
   ├─ use fresh element_token
   ▼
Cua Driver
   ▼
macOS Accessibility / Screen Capture / Input
```

The planner should prefer:

```text
bundle_id / application
window_title
element_role
element_name
```

The initial planner must not fabricate:

```text
process_id
window_id
element_token
snapshot_id
pixel x/y
```

Exact identifiers are accepted only when they came from an actual observation or trusted upstream adapter.

### Selector ambiguity

Semantic target resolution is fail-closed:

```text
0 matching apps/windows/elements → error
1 matching item                 → proceed
>1 matching items               → ambiguity error
```

This follows the accessibility-first lessons from Agent Desktop/Open Computer Use and avoids arbitrary "first match" behavior.

### Snapshot generation and stale targets

Cua element identities are tied to fresh window state. SystemAI therefore uses one named desktop session for observation and action and prefers the returned `element_token`. Bare element indexes are rejected unless paired with a matching snapshot generation.

Recovery classifies stale-token/snapshot errors separately from true accessibility failure so later V0.3 recovery can refresh the exact window rather than immediately dropping to blind pixels.

## 10. V0.2 verification path

Desktop action results do not self-certify success.

```text
Action returns
   ↓
Verifier
   ↓
fresh desktop observation
   ↓
application/window/element/value postcondition
```

Supported fresh desktop checks:

```text
application.running
window.exists
ui.element_exists
ui.element_value_equals
```

This allows a static task plan to use semantic identities while runtime resolution handles ephemeral OS identifiers.

## 11. Persistent data minimization

Screenshots and large observation payloads are useful transiently but should not automatically become long-lived memory.

Before writing audit or trajectory data, SystemAI recursively redacts known base64/image fields and oversized strings, retaining a SHA-256 digest and size metadata. Live task state can still carry transient screenshot data long enough for perception or verification.
