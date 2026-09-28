# Privileged Helper (deferred implementation)

The V3 architecture requires a separate narrow Rust privileged helper for explicitly approved elevated operations. It is **not part of the V1 release scope defined for this build**. V1 deliberately has no general root/admin shell.

When implemented, the helper accepts only typed operation IDs, validated parameters, a signed short-lived capability token, approved scope, expiration, and nonce. It never receives prompts, web content, or arbitrary shell text.
