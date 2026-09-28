# Implementation status

## V0.1 — core foundation

- [x] Typed task/action/result/verification contracts
- [x] Task DAG + cycle detection
- [x] Explicit task state machine
- [x] Capability registry and graph foundation
- [x] Risk/policy kernel
- [x] Filesystem scope control
- [x] Approval workflow
- [x] Short-lived capability tokens
- [x] Replaceable execution gateway
- [x] Bounded local executor
- [x] Optional Playwright browser adapter
- [x] Independent verifier
- [x] Recovery decisions
- [x] Hash-chained audit ledger
- [x] SQLite trajectories/memory
- [x] Event bus + basic process collector
- [x] Structured planner + OpenAI adapter
- [x] FastAPI local API
- [x] React/Tauri shell scaffold

## V0.2 — macOS desktop execution — implemented

- [x] Cua Driver CLI client behind a SystemAI adapter boundary
- [x] Driver readiness and macOS permission status model
- [x] Application discovery normalization
- [x] Window discovery normalization
- [x] Window/desktop snapshot normalization
- [x] Fresh semantic accessibility element resolution
- [x] Fresh `element_token` preference
- [x] Reject bare/stale element indexes without snapshot identity
- [x] Exact window/desktop action targets
- [x] Background-first input delivery
- [x] Ambiguous app/window/element selectors fail closed
- [x] Semantic desktop action capabilities
- [x] Independent application/window/element/value verification
- [x] Recovery classification for stale tokens and changed targets
- [x] Persistent screenshot/base64 redaction
- [x] Desktop readiness API endpoints
- [x] Read-only `desktop_doctor.py`
- [x] UI desktop readiness indicator
- [x] Semantic desktop DAG integration test

### V0.2 validation still required on target Mac

Run the live acceptance matrix after installing Cua Driver and granting Accessibility + Screen Recording:

1. TextEdit: launch → resolve window → set text → verify value.
2. Calculator: launch → semantic button actions → verify display.
3. Finder: list/open a controlled test directory without destructive actions.
4. Chrome: inspect an existing logged-in window without sending/publishing data.
5. Stale-element test: snapshot → force UI change → ensure old token is refused → refresh.
6. Ambiguity test: create duplicate labels → ensure SystemAI refuses to guess.

## V0.3 — next: visual grounding + recovery controller

1. Multimodal screenshot grounding inspired by Agent-S reflection.
2. Previous observation + previous action + current observation context.
3. Vision proposes only typed `ActionIntent`; never host Python/code.
4. Accessibility degraded → screenshot grounding fallback.
5. Fresh screenshot coordinates tied to snapshot/window generation.
6. Browser DOM → desktop accessibility → vision fallback ladder.
7. Implement actual replan/recovery continuation instead of only recovery classification.

## V0.4 — capability discovery

1. Discover installed apps and their observable capabilities.
2. Build app → capability → resource relations.
3. Track process/service/port dependencies.
4. Persist capability graph snapshots and changes.
5. Add application-specific adapters only where native/official APIs outperform GUI control.

## V0.5 — autonomous diagnosis

1. Hypothesis generator.
2. Read-only diagnostic probes first.
3. Evidence scoring and competing hypotheses.
4. Remediation plans through the normal policy kernel.
5. Independent health verification after remediation.

## V0.6 — skill compiler

1. Mine repeated successful trajectories.
2. Generalize variable inputs/resources.
3. Generate candidate skills.
4. Evaluate against deterministic fixtures/sandboxes.
5. Publish only above a reliability threshold.

## V0.7 — privileged helper

Rust native helper with:
- capability-token verification;
- operation allowlist;
- exact resource scope;
- expiry/nonces;
- OS authorization UI where required;
- no generic privileged command endpoint.

## V0.8 — continuous autonomous monitor

Collectors for files, apps, crashes, ports, network, disk, CPU/memory and permissions. Rule/anomaly filters run before invoking expensive AI diagnosis.

## V1.0 target

A local-first SystemAI capable of long cross-application workflows, common system/project diagnosis and repair, UI recovery, verified procedural memory and auditable policy-controlled autonomy.
