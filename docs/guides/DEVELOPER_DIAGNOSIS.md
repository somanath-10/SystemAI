# first release Developer Diagnosis Workflow

## Goal

The first product wedge answers:

> Find why this project is not running and fix it.

## Inputs

- project directory;
- optional `.systemai/project.json` manifest;
- user goal;
- autonomy mode.

## Read-only inspection

SystemAI inspects:

- source/project root;
- Git branch/status/recent commits;
- package manifests and basic dependency state;
- environment key shape, never secret values;
- expected/listening port and owning PID/process metadata;
- declared health endpoint;
- bounded log tails;
- optional service/container/database reachability.

## Evidence-backed diagnoses implemented in first release

### Already healthy

If the configured health endpoint is healthy, SystemAI completes without mutation.

### Missing required environment keys

SystemAI reports the missing key names and stops. It does not invent a secret or copy placeholder values as if they were valid credentials.

### Port conflict

If the expected port is occupied while the configured health endpoint is unhealthy:

1. identify the exact PID/process/create-time;
2. propose `process.terminate`;
3. Security Kernel classifies it high risk;
4. user approves exact action;
5. terminate and independently verify PID is gone;
6. start the declared project command (project provenance causes a separate approval);
7. verify process/port;
8. verify health endpoint.

### Process not running

When no listener exists and a start command is declared, first release can propose starting it and verify the result.

### No safe start contract

If the project is unhealthy but no explicit/auto-detected start command exists, SystemAI reports the blocker instead of guessing an arbitrary command.

## Manifest

Recommended explicit manifest:

```json
{
  "name": "api",
  "runtime": "python",
  "start": ["python", "app.py"],
  "test": ["pytest", "-q"],
  "cwd": ".",
  "expected_port": 8000,
  "health_url": "http://127.0.0.1:8000/health",
  "required_env": ["DATABASE_URL"],
  "log_files": ["app.log"]
}
```

Repository manifests are observations, not authority. first release marks command provenance as untrusted and asks for approval before executing it.

## Why this is a good first product wedge

It exercises the architecture with operations that are:

- structured;
- measurable;
- mostly local;
- independently verifiable;
- sandboxable;
- useful to developers;
- suitable for deterministic evaluation.
