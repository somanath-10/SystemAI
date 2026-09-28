# Extending SystemAI

This guide explains the preferred way to add functionality without creating a second authority path.

## Add a capability

1. Add a `CapabilityDefinition` in the registry.
2. Define canonical risk, reversibility, permissions, scope model, idempotency and supported verifiers.
3. Implement the executor behind the Execution Gateway.
4. Require a signed capability token in the executor.
5. Emit an `Observation` or structured result.
6. Add an independent verifier.
7. Add unit, integration, failure and security tests.
8. Document the capability and its limitations.

Never add a direct helper callable by the planner that mutates host state without the Security Kernel.

## Add an executor backend

Implement the backend-specific adapter but keep `ActionIntent` semantic. Native PIDs, window IDs, DOM handles or element references are resolved immediately before execution and are not durable planner state.

Examples:

- `CuaExecutor`
- `PlaywrightExecutor`
- `GitHubApiExecutor`
- `DatabaseExecutor`

## Add a diagnosis probe

A probe should be read-only where possible and return structured evidence rather than prose. Examples: port owner, service status, package version, missing environment key, health endpoint response.

The diagnosis layer forms hypotheses; probes do not autonomously remediate.

## Add a repair

Repairs are normal capabilities. They require:

- narrow scope;
- rollback/compensation where possible;
- canonical approval policy;
- before/after verification;
- provenance constraints.

## Add a model provider

Model providers belong behind the planner/provider interface. The provider may propose DAGs or typed actions but never owns authority. Cloud calls must eventually pass through the egress/privacy policy introduced in later versions.

## Add a UI page

The UI reads projections/events through the local control API/IPC. It must not bypass the kernel or executor to perform system actions.

## Add a skill in later releases

Do not mark a successful trajectory as trusted. Candidate skills must pass provenance analysis, static capability analysis, sandbox replay, regression tests, policy review and signing before unattended execution.
