# SystemAI V1 Known Limitations

This file is intentionally explicit so the codebase is not confused with the final universal SystemAI vision.

## Rust kernel execution

The production Rust Security Kernel source is included, but the build environment used to create this ZIP did not have a Rust/Cargo toolchain. The executable local tests therefore use the strict Python reference kernel. Production deployment must move the private signing authority into the Rust process and authenticated local IPC.

## Desktop

Existing V0.2 Cua/macOS code is retained but V1 does not claim the new V3 security model has been validated against real Finder/TextEdit/Calculator/Chrome on a Mac in this environment.

## Browser

Playwright scaffolding is retained. Dedicated SystemAI browser profile, Secret Broker/origin enforcement, helper sandbox and repair-on-drift are V2 work.

## Sandbox

V1 command execution is argv-only and bounded. Strong network/filesystem isolation profiles fail closed if Docker/bwrap/firejail/platform sandbox is unavailable. `READ_ONLY` in the reference runtime is a bounded subprocess profile and is not a complete OS security sandbox on every platform.

## Planner

V1 uses the deterministic developer-diagnosis planner. A frontier structured planner adapter exists in earlier code but is not required for V1 acceptance and was not live-API tested here.

## Cost routing/local models

The permanent local-first cost architecture is documented, but ModelRouter/local LLM/VLM and cost optimization are intentionally scheduled after baseline reliability measurement.

## Skills

Skill registry foundations from older code remain, but provenance-qualified/signed skill compilation is V3.

## Monitoring/voice/multi-device

Later versions.

## Cross-platform

Core contracts are platform neutral; Windows/Linux are not considered production complete.
