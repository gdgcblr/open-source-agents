import assert from 'node:assert/strict';
import test from 'node:test';
import { createAgentLogger, type LogEvent } from '../src/index.js';

function setup(captureContent = false): {
  events: LogEvent[];
  logger: ReturnType<typeof createAgentLogger>;
} {
  const events: LogEvent[] = [];
  return {
    events,
    logger: createAgentLogger({
      captureContent,
      sink: {
        write: (event) => {
          events.push(event);
        },
      },
    }),
  };
}

test('generic wrapper supports workflow and retrieval calls with typed inputs', async () => {
  const fixture = setup(true);
  const logger = await fixture.logger;
  const retrieve = logger.wrap('retrieve', 'retrieval', (query: string) => [query]);
  const workflow = logger.wrap('research', 'workflow', async (topic: string) =>
    retrieve(topic),
  );
  assert.deepEqual(await workflow('agent observability'), ['agent observability']);
  await logger.close();
  assert.equal(fixture.events.length, 4);
  assert.equal(fixture.events[1]?.parentSpanId, fixture.events[0]?.spanId);
});

test('stream wrapper is lazy, propagates values, and records consumer cancellation', async () => {
  const fixture = setup();
  const logger = await fixture.logger;
  let entered = false;
  async function* source(): AsyncGenerator<string> {
    entered = true;
    yield 'first';
    yield 'second';
  }
  const stream = logger.stream('response', 'model', source());
  assert.equal(entered, false);
  assert.equal(fixture.events.length, 0);
  for await (const value of stream) {
    assert.equal(value, 'first');
    break;
  }
  await logger.close();
  assert.equal(fixture.events.at(-1)?.status, 'interrupted');
});

test('streams preserve source exceptions and nested tool context', async () => {
  const fixture = setup();
  const logger = await fixture.logger;
  const original = new Error('stream failed');
  const tool = logger.wrapTool('fetch', () => 'chunk');
  async function* source(): AsyncGenerator<string> {
    yield await tool();
    throw original;
  }
  await assert.rejects(
    async () => {
      for await (const chunk of logger.stream('stream', 'model', source()))
        assert.equal(chunk, 'chunk');
    },
    (error) => error === original,
  );
  await logger.close();
  assert.equal(
    fixture.events.find((event) => event.kind === 'tool')?.parentSpanId,
    fixture.events[0]?.spanId,
  );
  assert.equal(fixture.events.at(-1)?.status, 'failed');
});

test('provider usage retains only reported counters and overwrites cumulative updates', async () => {
  const fixture = setup();
  const logger = await fixture.logger;
  await logger.trace('gemini', 'model', (span) => {
    span.recordUsage('gemini', {
      usageMetadata: { promptTokenCount: 3, candidatesTokenCount: 1, totalTokenCount: 4 },
    });
    span.recordUsage('gemini', {
      usageMetadata: { promptTokenCount: 3, candidatesTokenCount: 5, totalTokenCount: 8 },
    });
  });
  await logger.trace('openai', 'model', (span) =>
    span.recordUsage('openai', {
      usage: { input_tokens: 5, output_tokens: 6, total_tokens: 11 },
    }),
  );
  await logger.trace('anthropic', 'model', (span) =>
    span.recordUsage('anthropic', { usage: { input_tokens: 2, output_tokens: 4 } }),
  );
  await logger.trace('unknown', 'model', (span) => span.recordUsage('gemini', {}));
  await logger.close();
  const content = JSON.stringify(
    fixture.events.filter((event) => event.phase === 'finished'),
  );
  assert.match(content, /"totalTokens":8/);
  assert.match(content, /"totalTokens":11/);
  assert.match(content, /"status":"unavailable"/);
  assert.ok(!content.includes('"totalTokens":6'));
});

test('a hung sink has bounded shutdown and cannot change the operation result', async () => {
  const diagnostics: string[] = [];
  const logger = await createAgentLogger({
    writeTimeoutMs: 20,
    onDiagnostic: (code) => diagnostics.push(code),
    sink: { write: () => new Promise(() => {}) },
  });
  assert.equal(await logger.wrapTool('answer', () => 42)(), 42);
  const status = await logger.close();
  assert.equal(status.success, false);
  assert.equal(status.pending, 0);
  assert.ok(diagnostics.includes('write_timeout'));
});

test('completed stream captures explicitly selected output and contains hook failures', async () => {
  const fixture = setup(true);
  const logger = await fixture.logger;
  const source = async function* (
    span: import('../src/index.js').AgentSpan,
  ): AsyncGenerator<string> {
    span.captureOutput('Visible story only');
    yield 'first';
    yield 'second';
  };
  const chunks: string[] = [];
  for await (const chunk of logger.stream('response', 'model', source, {
    onChunk: async () => {
      throw new Error('private-hook-error');
    },
  }))
    chunks.push(chunk);
  await logger.close();
  assert.deepEqual(chunks, ['first', 'second']);
  assert.equal(fixture.events.at(-1)?.status, 'completed');
  const content = JSON.stringify(fixture.events);
  assert.match(content, /Visible story only/);
  assert.match(content, /chunk_hook_failed/);
  assert.ok(!content.includes('private-hook-error'));
});

test('source failure survives a second failure during iterator cleanup', async () => {
  const fixture = setup();
  const logger = await fixture.logger;
  const original = new Error('source failure');
  const source: AsyncIterable<string> = {
    [Symbol.asyncIterator]: () => ({
      next: async () => {
        throw original;
      },
      return: async () => {
        throw new Error('cleanup failure');
      },
    }),
  };
  await assert.rejects(
    async () => {
      for await (const chunk of logger.stream('source', 'model', source))
        assert.ok(chunk);
    },
    (error) => error === original,
  );
  await logger.close();
  assert.equal(fixture.events.at(-1)?.status, 'failed');
});

test('manual usage ignores getters and invalid counters; closed loggers still run wrapped tools', async () => {
  const fixture = setup();
  const logger = await fixture.logger;
  let getterInvoked = false;
  const response = Object.defineProperty({}, 'usageMetadata', {
    get: () => {
      getterInvoked = true;
      throw new Error('must not execute');
    },
  });
  await logger.trace('model', 'model', (span) => {
    assert.equal(span.recordUsage('gemini', response).status, 'unavailable');
    assert.equal(
      span.recordUsage('openai', {
        usage: {
          input_tokens: -1,
          output_tokens: NaN,
          total_tokens: Number.MAX_SAFE_INTEGER + 1,
        },
      }).status,
      'unavailable',
    );
  });
  assert.equal(getterInvoked, false);
  await logger.close();
  assert.equal(await logger.wrapTool('late', () => 42)(), 42);
  assert.equal((await logger.flush()).dropped, 1);
});

test('a hung close and a failing diagnostic callback remain bounded and non-fatal', async () => {
  const logger = await createAgentLogger({
    writeTimeoutMs: 10,
    sink: { write: () => {}, close: () => new Promise(() => {}) },
    onDiagnostic: () => {
      throw new Error('diagnostic failed');
    },
  });
  await logger.run('task', () => 42);
  assert.equal((await logger.close()).success, false);
});
