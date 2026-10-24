import assert from 'node:assert/strict';
import { mkdtemp, readFile, stat, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { createAgentLogger, type LogEvent, type LogSink } from '../src/index.js';

function memorySink(): { events: LogEvent[]; sink: LogSink } {
  const events: LogEvent[] = [];
  return {
    events,
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  };
}

test('concurrent tool wrappers retain separate run parents, results, and receivers', async () => {
  const { events, sink } = memorySink();
  const logger = await createAgentLogger({ sink });
  const receiver = {
    factor: 2,
    multiply: logger.wrapTool(
      'multiply',
      function (this: { factor: number }, value: number): number {
        return this.factor * value;
      },
    ),
  };
  await Promise.all(
    [1, 2].map((value) =>
      logger.run('task', async () => {
        assert.equal(await receiver.multiply(value), value * 2);
      }),
    ),
  );
  await logger.close();
  const tools = events.filter(
    (event) => event.kind === 'tool' && event.phase === 'started',
  );
  assert.equal(tools.length, 2);
  assert.notEqual(tools[0]?.parentSpanId, tools[1]?.parentSpanId);
  assert.equal(new Set(events.map((event) => event.sequence)).size, events.length);
  assert.equal(events.filter((event) => event.phase === 'finished').length, 4);
});

test('metadata defaults exclude content and preserve the original application error', async () => {
  const { events, sink } = memorySink();
  const logger = await createAgentLogger({ sink });
  const original = new Error('secret=should-not-be-stored');
  const tool = logger.wrapTool('failing', () => {
    throw original;
  });
  await assert.rejects(tool(), (error) => error === original);
  await logger.flush();
  const content = JSON.stringify(events);
  assert.ok(!content.includes('should-not-be-stored'));
  assert.equal(events.at(-1)?.status, 'failed');
  await logger.close();
});

test('opted-in content redacts sensitive keys, credentials, cycles, and getters', async () => {
  const { events, sink } = memorySink();
  const logger = await createAgentLogger({ sink, captureContent: true });
  const input: Record<string, unknown> = {
    password: 'private-value',
    nested: { authorization: 'token' },
    message: 'Bearer abcdefghijklmnop',
    thought: 'hidden',
  };
  input.self = input;
  Object.defineProperty(input, 'danger', {
    enumerable: true,
    get: () => {
      throw new Error('getter executed');
    },
  });
  const span = logger.startSpan('lookup', 'tool', { input });
  span.end('completed', { api_key: 'private-key', ok: true });
  await logger.close();
  const content = JSON.stringify(events);
  for (const value of ['private-value', 'private-key', 'abcdefghijklmnop', 'hidden'])
    assert.ok(!content.includes(value));
  assert.match(content, /REDACTED/);
  assert.match(content, /CIRCULAR/);
});

test('sink failure does not affect tools and is visible in delivery status', async () => {
  const logger = await createAgentLogger({
    sink: {
      write: () => {
        throw new Error('disk failure');
      },
    },
  });
  assert.equal(await logger.wrapTool('answer', () => 42)(), 42);
  const result = await logger.close();
  assert.equal(result.success, false);
  assert.equal(result.failed, 2);
});

test('writes private JSONL files and rejects a symlink output directory', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-logger-test-'));
  const logger = await createAgentLogger({ directory: join(directory, 'logs') });
  await logger.run('task', async () => 'done');
  assert.equal((await logger.close()).success, true);
  assert.ok(logger.filePath);
  const lines = (await readFile(logger.filePath, 'utf8')).trim().split('\n');
  assert.equal(lines.length, 2);
  assert.equal((await stat(logger.filePath)).mode & 0o777, 0o600);
  await symlink(join(directory, 'logs'), join(directory, 'linked'));
  await assert.rejects(createAgentLogger({ directory: join(directory, 'linked') }));
  await writeFile(join(directory, 'not-directory'), 'data');
  await assert.rejects(
    createAgentLogger({ directory: join(directory, 'not-directory') }),
  );
});

test('close marks abandoned spans interrupted; queue overflow is reported', async () => {
  const events: LogEvent[] = [];
  let release: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const logger = await createAgentLogger({
    maxPendingEvents: 1,
    sink: {
      write: async (event) => {
        await gate;
        events.push(event);
      },
    },
  });
  logger.startSpan('unfinished', 'run');
  logger.startSpan('dropped', 'tool');
  release?.();
  const result = await logger.close();
  assert.equal(result.success, false);
  assert.ok(result.dropped > 0);
});

test('active span limits drop telemetry while preserving tool execution', async () => {
  const { sink } = memorySink();
  const logger = await createAgentLogger({ sink, maxActiveSpans: 1 });
  const span = logger.startSpan('held', 'run');
  assert.equal(await logger.wrapTool('answer', () => 42)(), 42);
  span.end();
  const status = await logger.close();
  assert.equal(status.success, false);
  assert.equal(status.dropped, 1);
});

test('file quota and invalid configuration are explicit failures', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-log-quota-'));
  const logger = await createAgentLogger({ directory, maxFileBytes: 1024 });
  for (let index = 0; index < 5; index++)
    await logger.run('bounded-run', async () => index);
  const result = await logger.close();
  assert.equal(result.success, false);
  assert.ok(result.failed > 0);
  await assert.rejects(createAgentLogger({ maxPendingEvents: 0 }));
  await assert.rejects(createAgentLogger({ sink: memorySink().sink, directory }));
});

test('abandoned span close is idempotent and delivers an interrupted terminal event', async () => {
  const { events, sink } = memorySink();
  let closes = 0;
  const logger = await createAgentLogger({
    sink: {
      ...sink,
      close: () => {
        closes++;
      },
    },
  });
  const span = logger.startSpan('unfinished', 'run');
  const first = logger.close();
  assert.equal(logger.close(), first);
  assert.equal((await first).success, true);
  span.end();
  assert.equal(closes, 1);
  assert.equal(events.length, 2);
  assert.equal(events[1]?.status, 'interrupted');
});
