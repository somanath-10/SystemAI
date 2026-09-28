# macOS desktop implementation — V0.2

SystemAI V0.2 uses Cua Driver through a thin CLI adapter. SystemAI Core does not own macOS Accessibility or Screen Recording permissions directly. On macOS, the stable CuaDriver.app daemon owns those grants and SystemAI talks to it through the `cua-driver` command.

## Why this design

macOS TCC permissions are attributed to a responsible application identity. Keeping the driver behind its signed app/daemon avoids granting broad desktop access to arbitrary Python subprocesses. SystemAI still applies its own capability registry, policy kernel, audit, verification, and recovery logic above the driver.

## Setup on a Mac

Install Cua Driver using its official installer/documentation, then start the app-owned daemon:

```bash
open -n -g -a CuaDriver --args serve
```

Grant Accessibility and Screen Recording through the driver-owned permission flow:

```bash
cua-driver permissions grant
cua-driver permissions status --json
```

Verify the driver before enabling SystemAI:

```bash
cua-driver status
cua-driver doctor
cua-driver call list_apps '{}'
```

Then enable the SystemAI adapter:

```bash
export SYSTEMAI_ENABLE_DESKTOP=true
export SYSTEMAI_DESKTOP_BACKEND=cua-cli
export SYSTEMAI_DESKTOP_SESSION=systemai
```

Run the read-only SystemAI doctor:

```bash
PYTHONPATH=src python scripts/desktop_doctor.py
```

## V0.2 action policy

SystemAI does not let the planner fabricate ephemeral desktop identifiers.

The planner should describe semantic targets:

```json
{
  "bundle_id": "com.apple.TextEdit",
  "window_title": "Untitled",
  "element_role": "AXTextArea",
  "element_name": "Editor"
}
```

The trusted executor resolves these immediately before the action:

```text
semantic app selector
  -> current PID
  -> current matching window
  -> fresh get_window_state
  -> unique matching accessibility element
  -> fresh element_token
  -> action
  -> fresh verification snapshot
```

If the app, window, or element selector matches zero or multiple objects, SystemAI fails closed instead of guessing.

## Addressing priority

```text
fresh accessibility element token
  > snapshot_id + element_index
  > explicit pixel coordinates from an observed screenshot
```

Bare element indexes are rejected because a later snapshot may invalidate them. Pixel coordinates are never invented by the initial planner.

## Implemented desktop capabilities

- `application.list`
- `application.launch`
- `window.list`
- `window.observe`
- `window.activate`
- `ui.observe`
- `ui.click`
- `ui.set_value`
- `ui.scroll`
- `ui.drag`
- `keyboard.hotkey`
- `keyboard.type`
- `screen.capture`

## Independent verification

The verifier can take a new driver observation for:

- `application.running`
- `window.exists`
- `ui.element_exists`
- `ui.element_value_equals`

The verification snapshot is separate from the action result. A driver's `completed` response therefore does not automatically mark the task step successful.

## Privacy

Live screenshots may exist briefly in an action result for perception/verification, but screenshot/base64 fields and oversized text are redacted before audit or long-term trajectory persistence. The audit log stores hashes and metadata instead of full screenshot content.

## Current boundary

V0.2 integrates the real desktop driver contract and can operate a Mac when run there. This Linux build container cannot grant or exercise macOS TCC permissions, so the actual Finder/TextEdit/Calculator/Chrome acceptance suite must be executed on the target Mac.
