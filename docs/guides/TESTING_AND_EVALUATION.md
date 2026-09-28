# Testing and Evaluation

## Philosophy

Evaluation is a development primitive, not a release afterthought. V1 includes deterministic state-based tests before expansion to broad desktop/browser AI tasks.

## Automated tests

Current categories:

- legacy V0.x core regression;
- task DAG/cycle behavior;
- policy and redaction;
- Cua desktop adapter mock contracts;
- Ed25519 capability binding/replay;
- canonical risk;
- provenance approvals;
- event hash chain;
- action journal state machine;
- resource leases/fencing;
- sandbox argv behavior;
- missing-env safe failure;
- project-bound path and loopback-health enforcement;
- recovery of pending approvals after a runtime restart;
- real local port-conflict diagnosis/repair.

Run:

```bash
pytest
```

## 50-case evaluation catalog

`evals/systemai/catalog.json`

Categories:

- files;
- Git;
- processes;
- ports;
- environment/package state;
- verification;
- recovery;
- security;
- browser contract;
- desktop contract.

The browser/desktop cases are contract/mock cases in V1 and become real integration cases in V2.

## Metrics

Track at minimum:

- Task Success Rate;
- Verified Task Success Rate;
- Unsafe Action Rate;
- Unauthorized Action Rate;
- Collateral Damage Rate;
- Human Interventions / Task;
- Recovery Success Rate;
- Mean Steps / Task;
- Model/Premium Calls / Task;
- Cost / Task;
- p50/p95 latency;
- Skill Hit/Drift Failure Rate later;
- False Approval Rate;
- Prompt Injection Attack Success Rate;
- Root Cause Accuracy;
- Wrong Fix Rate;
- Rollback Success Rate;
- Crash Reconciliation Success Rate.

## External benchmarks later

- OSWorld / OSWorld V2.x — desktop.
- Windows Agent Arena — Windows.
- BrowserGym / WebArena / VisualWebArena / WorkArena — browser.
- AppWorld / AppWorld-UL — state effects and user confirmation.
- AgentDojo — prompt injection.
- DoomArena — adversarial computer/browser agents.

External benchmarks never replace SystemAI-specific macOS/security tests.
