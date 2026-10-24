# Agent Logger

Local execution logs for AI agents. A TypeScript SDK that records model calls,
tool execution, streams, and nested workflows with an optional Google ADK plugin.

[npm](https://www.npmjs.com/package/@manohareldhandi/agent-logger) ·
[MIT license](LICENSE)

## Overview

Agent Logger helps developers understand which operations ran, how long they took,
and where they failed. Instrument existing functions or register the ADK plugin;
inspect the resulting JSONL files with the included command-line viewer.

- Correlate nested operations with run IDs, span IDs, and parent relationships.
- Preserve function arguments, results, and original errors through async wrappers.
- Trace async streams, including source failures and early consumer exit.
- Normalize provider-reported Gemini, OpenAI, and Anthropic token usage.
- Keep content capture opt-in, with bounded redaction and private local files.
- Use bounded queues and storage timeouts without replacing application results.
- Export sanitized events through a custom sink when local files are insufficient.

The core has zero runtime dependencies and requires no account, collector, or API
key. It supports Node.js 22.13+ and ESM. CommonJS applications can use dynamic
`import()`. Google ADK is an optional peer dependency, tested with version 2.3.0.

## Install

```sh
npm install @manohareldhandi/agent-logger
```

## Quick start

Save this as `example.mjs` and run `node example.mjs`:

```js
import { createAgentLogger } from '@manohareldhandi/agent-logger';

const logger = await createAgentLogger();
const lookup = logger.wrapTool('lookup', async (topic) => ({ topic, found: true }));

try {
  const result = await logger.run('research', () => lookup('agent logging'));
  console.log(result);
} finally {
  const delivery = await logger.close();
  console.log('Log:', logger.filePath);
  if (!delivery.success) console.warn('Incomplete log:', delivery);
}
```

The result is `{ topic: 'agent logging', found: true }`. The log contains start
and finish events for the run and tool, linked by their run and parent span IDs.
Arguments and outputs are omitted by default.

Use the printed file path to inspect the recorded operations:

```sh
npx agent-logger view .agent-logs/<printed-file-name>.jsonl
```

Call `close()` after application work finishes to drain writes and close storage.
Wrappers always return promises, including when the original function is synchronous.

## Integration

### Functions and workflows

Use `logger.wrap(name, kind, fn)` for functions in an existing agent system, or
`logger.trace(name, kind, operation, options)` for explicit instrumentation.
Supported kinds are `run`, `agent`, `model`, `tool`, `workflow`, `retrieval`,
`embedding`, `memory`, and `custom`.

Nested calls inherit context automatically. Concurrent runs keep separate parents.
Callback integrations can use `logger.startSpan()` and explicitly call `span.end()`.

### Model calls and usage

Wrap an existing model client and report usage from its actual response:

```ts
const answer = await logger.trace('generate', 'model', async (span) => {
  const response = await modelClient.models.generateContent({ model, contents: prompt });
  span.recordUsage('gemini', response);
  return response.text;
});
```

`recordUsage()` accepts Gemini GenerateContent, OpenAI Responses/Chat Completions,
and Anthropic Messages responses. Missing counters remain unavailable. Repeated
cumulative updates replace the span's earlier usage; token totals and prices are
never estimated. `normalizeUsage()` is also available as a standalone function.

To capture selected inputs and outputs, create the logger with
`captureContent: true` and pass `{ input: prompt }` as the fourth `trace()` argument.
Explicit attributes are sanitized even when content capture is disabled.

### Streams

```ts
for await (const chunk of logger.stream('answer', 'model', responseStream)) {
  // Process the original chunk.
}
```

Streams start lazily and preserve context for nested operations. Source failures
are rethrown unchanged; early consumer exit closes the source iterator and records
interruption. An optional `onChunk(chunk, span)` hook can report provider usage or
call `span.captureOutput(text)` for selected visible output when capture is enabled.
Hook failures produce a capture-gap marker without replacing the source result.

### Google ADK

```sh
npm install @google/adk@2.3.0
```

Register the plugin on a runner that uses your existing agent:

```ts
import { InMemorySessionService, Runner } from '@google/adk';
import { createAgentLogger } from '@manohareldhandi/agent-logger';
import { AgentLoggerPlugin } from '@manohareldhandi/agent-logger/adk';

const logger = await createAgentLogger();
const plugin = new AgentLoggerPlugin(logger);
const runner = new Runner({
  appName: 'my_app',
  agent: yourAgent,
  sessionService: new InMemorySessionService(),
  plugins: [plugin],
  autoCreateSession: true,
});

try {
  for await (const event of runner.runAsync({
    userId: 'user1',
    sessionId: 'session1',
    newMessage: { role: 'user', parts: [{ text: 'Hello' }] },
  })) {
    // Handle the original ADK event.
  }
} finally {
  const delivery = await plugin.close();
  if (!delivery.success) console.warn('Incomplete log:', delivery);
}
```

The plugin records invocation, model, and tool callbacks while preserving ADK's
results and error recovery. Agent scopes group observed callbacks; their duration
represents the observed interval. `plugin.close()` also finalizes abandoned runs.

## Configuration

Pass options to `createAgentLogger()`:

| Option             | Default          | Purpose                                             |
| ------------------ | ---------------- | --------------------------------------------------- |
| `directory`        | `.agent-logs`    | Private local output directory                      |
| `captureContent`   | `false`          | Capture explicit, redacted inputs and outputs       |
| `maxPendingEvents` | `256`            | Maximum queued events                               |
| `maxActiveSpans`   | `1024`           | Maximum tracked concurrent spans                    |
| `maxFileBytes`     | `16777216`       | Per-file limit in bytes                             |
| `writeTimeoutMs`   | `2000`           | Timeout for each sink write or close                |
| `sink`             | Local JSONL file | Custom `LogSink` with `write(event)` and `close?()` |
| `onDiagnostic`     | None             | Callback receiving diagnostic codes                 |

`flush()` drains the current queue. `close()` also closes storage and marks open
spans interrupted. Both return `success`, `written`, `failed`, `dropped`, and
`pending` delivery counters. Check these counters to detect incomplete logs.

Storage failures and queue overflow leave application work running. A timed-out
write has an unknown storage outcome; the sink is quarantined and no writes or
agent actions are retried. Create a new logger after repairing the sink.

Events include a schema version, sequence, timestamp, run/span identifiers, kind,
name, phase, and optional status, duration, and sanitized data. Use `readLog(path)`
to read validated version-1 events from a closed JSONL file up to 64 MiB.

## Examples and development

From the repository root:

```sh
cd tools/agent-logger
npm ci
npm run demo
```

The offline demo runs an ADK runner with a scripted model and a weather fixture
tool. It makes no network requests. Expected answer:

```text
Bengaluru: 25°C, clear.
```

It records one run, one agent scope, two model calls, and one tool call. Offline
token counters are fixtures and do not represent billed usage.

Live examples require a Google AI Studio key. Copy `.env.example` to `.env` if no
local environment file exists, then set `GOOGLE_API_KEY`:

| Variable         | Required               | Default                 |
| ---------------- | ---------------------- | ----------------------- |
| `GOOGLE_API_KEY` | For live examples only | None                    |
| `GEMINI_MODEL`   | No                     | `gemini-3.5-flash-lite` |

```sh
npm run demo:gemini
npm run demo:story
npm run demo:story -- --repo ../your-project
```

The Gemini demo uses ADK and a fixture weather tool. The story example uses the
Google Gen AI SDK directly, records provider usage, and calls a wrapped word-count
tool. It explicitly enables content capture. The optional `--repo` argument reads
bounded README/package excerpts for context without editing the repository.

Live examples send prompts and any selected repository excerpts to Google and may
incur API charges. Provider errors and empty answers exit nonzero. Logging itself
does not require environment variables or send data to a remote service.

## Validation

```sh
npm run check   # Formatting, lint, strict types, tests, and build
npm run verify  # Also checks privacy, dependency audit, and the packed SDK
```

Tests cover concurrent contexts, usage normalization, model/tool failures, original
error identity, redaction, private files, bounded queues, sink timeouts, streams,
the reader/CLI, story workflows, and an offline ADK integration. Package checks
install the archive in a temporary application and verify typed imports, CommonJS
dynamic import, the installed CLI, and an ADK model/tool run.

## Security and limitations

- Local files use mode `0600` in a `0700` directory. Existing output directories
  must have private permissions. Creation rejects a symlink output directory and
  exclusively creates a random filename; keep parent directories under your control.
- Content capture is disabled by default. Sensitive fields, common credential
  formats, private keys, and reasoning fields are filtered. Data depth, size, and
  collection lengths are bounded. Redaction is best effort; avoid logging secrets.
- Only instrumented operations are observed. A `completed` status indicates that
  an operation returned, without assessing the correctness of its answer.
- The SDK targets Node.js. Browser runtimes, native CommonJS `require()`, Python
  agents, ADK bidirectional sessions, and automatic full stream-text capture are
  outside its current scope.
- The ADK plugin retains up to 128 invocations; the oldest is marked interrupted
  with a capture-gap marker when the limit is reached.
- Pending events can be lost on process crash. File size limits do not manage
  retention; applications must remove old files as needed.
- Validated on macOS with Node.js 22.13.0 and 26.3.0. Windows filesystem permissions
  and flags are untested. Applications manage their own optional ADK dependency tree.

Environment files, local logs, generated builds, and archives are ignored by Git.
The npm package includes compiled JavaScript, type declarations, README, license,
and package metadata. Tests, examples, and source maps are excluded.

## License

MIT. See [LICENSE](LICENSE).
