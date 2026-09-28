# Security Policy

SystemAI controls real system resources. Security issues involving scope escape, token forgery, approval bypass, secret exposure, sandbox escape, unauthorized destructive actions or prompt-injection-to-authority escalation should be treated as high priority.

Do not publish real user secrets, tokens, keys, screenshots or private project data in a public issue.

## Design boundaries

- no normal unrestricted root/admin shell;
- no model-owned signing keys;
- high-risk actions require canonical approval;
- external/repository content is not trusted instruction;
- executor success does not replace verification;
- requested sandbox isolation fails closed if it cannot be enforced.

See `docs/security/SECURITY_MODEL.md` and `docs/security/THREAT_MODEL.md`.
