# Architecture — pinpoint-agent

Status: design. Modules are *planned* until written.

## Module Map

| Module | Responsibility |
| :--- | :--- |
| `src/index.js` | CLI entry. Parses flags by hand. REPL loop. Only file that writes to stdout. |
| `src/agent.js` | Turn loop, tool loop, confirmation gate, call cap. |
| `src/mcp-client.js` | Spawns the server with `process.execPath`, connects over stdio, `callTool` parses JSON payloads. |
| `src/guardrails.js` | Input clamp, allowlist, sessionId injection, output truncation, call cap. |
| `src/prompts.js` | System prompt (data-not-instructions rule). |
| `src/config.js` | Env loading (`process.loadEnvFile` when `.env` exists), validation, key redaction helper. |
| `src/constants.js` | Limits and model defaults. |
| `src/logger.js` | stderr logger. |
| `src/llm/mock.js` | Deterministic regex intent model. |
| `src/llm/gemini.js` | `@google/genai` adapter with manual function calling. |

## Turn Flow

```
human input
  └─▶ guardrails.clampInput
        ├─▶ record_message (role=user)            [agent code, not model]
        ├─▶ model.next({ systemPrompt, history, tools })
        │       ├─ text         → final reply
        │       └─ tool_calls   → allowlist check → sessionId injected → confirm gate?
        │                           → mcp-client.callTool → truncate → back to model
        └─▶ record_message (role=assistant)       [agent code, not model]
```

Model adapter interface: `createModel(config) → { name, next({ systemPrompt, history, tools }) }`, returning `{ type: 'text', text }` or `{ type: 'tool_calls', calls: [{ id, name, args }] }`.

## Gemini Adapter

Tools converted to `functionDeclarations` with `parametersJsonSchema`. Manual function calling so the agent enforces allowlist, confirmation and call caps. Function results return as `functionResponse` parts. Exact part shapes to be confirmed in `node_modules/@google/genai/dist/genai.d.ts` before coding.

## Ported vs new

New in this project. Concept of pin/bookmark/navigate comes from the server, which is adapted from ai-pinpoint.
