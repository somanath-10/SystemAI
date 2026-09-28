# Sandbox Profiles

contract profiles:

- `READ_ONLY`
- `WORKSPACE_WRITE_NO_NETWORK`
- `WORKSPACE_WRITE_ALLOWLIST_NETWORK`
- `TEMPORARY_CONTAINER_OR_VM`
- `APPROVED_ELEVATED_HOST_OPERATION`

The reference executor fails closed if a requested isolation profile cannot be enforced with an available backend. It never silently downgrades a requested strong sandbox to an unrestricted host command.
