## Why

Project documentation and deployed behavior drift independently. A README can
publish commands that fail, an API can violate its OpenAPI response schema, and
a built image can disagree with its declared Dockerfile settings. Maintainers
need repeatable observations with source locations, not a model's unsupported
judgment that a project looks correct.

## What Changes

- Add README execution/link, live OpenAPI response and Docker image-config checks.
- Add authoritative evidence reports, a Google ADK native Ollama adapter and CLI.
- Add the deliberately lying Notes fixture, uv lockfile, mise and Make targets.
- Preserve host source through a bind-mounted development container.
- Use native Ollama tool calling without LiteLLM or additional model backends.

## Capabilities

### New Capabilities

- `project-claims`: Bounded claim discovery; README command/link verification;
  live API contract checks; image-configuration comparison; authoritative reports;
  native Ollama agent orchestration; and a reproducible synthetic demonstration.

### Modified Capabilities

None.

## Impact

All implementation and dependencies are isolated to agents/claimcheck. The agent
index gains one entry. No other project, root runtime or external service changes.
