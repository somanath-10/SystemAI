# SystemAI Threat Model

## Assets to protect

- user files and data;
- credentials, tokens and private keys;
- external accounts and communications;
- OS security settings;
- installed applications and services;
- audit history;
- integrity of SystemAI policy/approval state.

## Trust classes

Trusted authority:
- explicit user requests;
- local/admin policy;
- signed capability/skill definitions;
- runtime-generated capability tokens.

Untrusted observations:
- webpages;
- emails/messages;
- PDFs/documents;
- terminal/process output;
- application UI text;
- clipboard data;
- downloaded files;
- model-generated text itself.

Untrusted content can influence reasoning as evidence, but cannot authorize capabilities.

## Primary threats

### Prompt injection

Mitigation:
- wrap external observations with explicit trust metadata;
- planner cannot bypass the policy kernel;
- high-risk actions require approval/capability tokens;
- no model-output-to-`eval`/`exec` host path.

### Confused-deputy / overbroad authority

Mitigation:
- capability-scoped actions;
- filesystem root scopes;
- short-lived action-bound tokens;
- separate privileged helper in future architecture.

### Stale/incorrect UI target

Mitigation:
- preserve window/element/generation identity;
- semantic selectors before coordinates;
- ambiguity must fail closed;
- re-observe before high-risk action.

### False-success hallucination

Mitigation:
- executor effect status is separate from independent verification;
- required postconditions block task completion.

### Credential leakage

Required future rule:
- model sees credential references only;
- OS keychain/secret broker injects secrets directly into approved target;
- do not store secrets in trajectories/audit payloads.

### Privilege abuse

Required architecture:
- LLM/runtime process never runs persistently as root/admin;
- privileged helper accepts only typed operations plus valid capability token;
- helper contains no prompt/model logic.

## Capabilities that should remain unavailable by default

- disabling security controls;
- bypassing UAC/TCC/MFA or other access controls;
- credential extraction/dumping;
- stealth persistence;
- hidden surveillance;
- arbitrary privileged shell execution.

These are not necessary for legitimate SystemAI autonomy.

## V0.2 desktop-specific threats

### Stale accessibility identities

**Threat:** the planner or runtime reuses an element index/token after the target window changes, causing an action to hit the wrong control.

**Mitigation:** semantic actions resolve against a fresh window snapshot; element tokens are preferred; bare indexes require snapshot identity; stale-token errors trigger refresh/re-resolve recovery rather than blind retry.

### Ambiguous UI controls

**Threat:** multiple controls share the same label and an agent chooses an arbitrary one.

**Mitigation:** semantic app/window/element resolution must produce exactly one match. Multiple matches fail closed and require a more specific selector or later visual reasoning.

### Coordinate confusion

**Threat:** mixing screen coordinates, window-local coordinates, and stale screenshots produces actions in the wrong location.

**Mitigation:** ActionTarget distinguishes exact window vs desktop display target. Initial planning is forbidden from inventing coordinates. Pixel input is reserved for coordinates derived from a current observation.

### Screenshot persistence/privacy

**Threat:** screen captures may contain credentials, private messages, health/financial data, or other sensitive content and leak into logs/memory.

**Mitigation:** screenshot/base64 fields and oversized observation strings are redacted before persistent audit/trajectory storage. Future vision storage should use explicit short-lived encrypted artifacts with retention limits.

### Driver permission expansion

**Threat:** an agent attempts to launch a new unrestricted desktop-control runtime or widen Cua permission mode.

**Mitigation:** V0.2 talks to an operator-installed/app-owned Cua daemon. Permission setup remains a human/operator action. The model is not given installation, permission-granting, or runtime-authorization controls as normal desktop tools.
