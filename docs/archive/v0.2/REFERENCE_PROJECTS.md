# Reference projects

These repositories were used as architectural references. SystemAI keeps third-party implementations behind adapters and should pin a reviewed commit before integrating any of them.

- Microsoft UFO / UFO Galaxy: https://github.com/microsoft/UFO
- Cua: https://github.com/trycua/cua
- Agent-S: https://github.com/simular-ai/Agent-S
- Open Interpreter: https://github.com/openinterpreter/openinterpreter
- Agent Desktop: https://github.com/crowecawcaw/agent-desktop
- Open Computer Use: https://github.com/opensymph/open-computer-use

## Integration rule

Before adding a runtime dependency:

1. record repository + exact commit SHA;
2. record license and required notices;
3. review security-sensitive execution paths;
4. wrap it behind a SystemAI interface;
5. add contract tests;
6. do not allow the dependency to make policy decisions on behalf of SystemAI Core.
