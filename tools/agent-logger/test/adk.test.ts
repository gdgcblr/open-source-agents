import assert from 'node:assert/strict';
import test from 'node:test';
import type { LlmResponse } from '@google/adk';
import { createAgentLogger, type LogEvent } from '../src/index.js';
import { AgentLoggerPlugin } from '../src/adk.js';
import { runExample } from '../examples/agent.js';
import { OfflineModel } from '../examples/offline-model.js';

test('actual ADK runner captures model/tool spans, usage, and parent relationships', async () => {
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  const result = await runExample(plugin, new OfflineModel());
  assert.match(result, /Bengaluru/);
  assert.equal((await plugin.close()).success, true);
  const finals = events.filter((event) => event.phase === 'finished');
  assert.equal(finals.filter((event) => event.kind === 'model').length, 2);
  assert.equal(finals.filter((event) => event.kind === 'tool').length, 1);
  assert.equal(finals.filter((event) => event.kind === 'agent').length, 1);
  assert.equal(finals.find((event) => event.kind === 'run')?.status, 'completed');
  assert.match(JSON.stringify(finals), /inputTokens/);
  assert.ok(
    finals.filter((event) => event.kind !== 'run').every((event) => event.parentSpanId),
  );
  assert.ok(!JSON.stringify(events).includes('What is the weather'));
});

test('ADK tool failure is logged while framework recovery remains unchanged', async () => {
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  assert.match(await runExample(plugin, new OfflineModel(), true), /Bengaluru/);
  await plugin.close();
  assert.equal(
    events.find((event) => event.kind === 'tool' && event.phase === 'finished')?.status,
    'failed',
  );
  assert.equal(
    events.find((event) => event.kind === 'run' && event.phase === 'finished')?.status,
    'completed',
  );
});

test('ADK model failure remains a framework error response and marks the run failed', async () => {
  const original = new Error('fixture model failed');
  class FailingModel extends OfflineModel {
    override async *generateContentAsync(): AsyncGenerator<LlmResponse, void> {
      throw original;
    }
  }
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  await assert.rejects(
    runExample(plugin, new FailingModel()),
    /provider could not complete/,
  );
  await plugin.close();
  assert.equal(
    events.find((event) => event.kind === 'model' && event.phase === 'finished')?.status,
    'failed',
  );
  assert.equal(
    events.find((event) => event.kind === 'run' && event.phase === 'finished')?.status,
    'failed',
  );
});

test('quota failure is actionable without retaining provider secrets', async () => {
  class QuotaModel extends OfflineModel {
    override async *generateContentAsync(): AsyncGenerator<LlmResponse, void> {
      throw new Error(
        JSON.stringify({
          error: {
            code: 429,
            status: 'RESOURCE_EXHAUSTED',
            message: 'quota exhausted; private-provider-marker',
          },
        }),
      );
    }
  }
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    captureContent: true,
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  await assert.rejects(runExample(plugin, new QuotaModel()), /quota or rate limit/);
  await plugin.close();
  const retained = JSON.stringify(events);
  assert.match(retained, /quota_exceeded/);
  assert.ok(!retained.includes('private-provider-marker'));
});

test('empty model response cannot masquerade as a successful demo', async () => {
  class EmptyModel extends OfflineModel {
    override async *generateContentAsync(): AsyncGenerator<LlmResponse, void> {
      yield { content: { role: 'model', parts: [] } };
    }
  }
  const logger = await createAgentLogger({ sink: { write: () => {} } });
  const plugin = new AgentLoggerPlugin(logger);
  await assert.rejects(runExample(plugin, new EmptyModel()), /without a visible answer/);
  await plugin.close();
});

test('ADK content opt-in filters thought parts, while core default remains metadata only', async () => {
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    captureContent: true,
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  await runExample(plugin, new OfflineModel());
  await plugin.close();
  assert.match(JSON.stringify(events), /Bengaluru/);
  assert.ok(!JSON.stringify(events).includes('internal-thought-marker'));
});

test('concurrent ADK invocations retain distinct trees', async () => {
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const plugin = new AgentLoggerPlugin(logger);
  await Promise.all([
    runExample(plugin, new OfflineModel()),
    runExample(plugin, new OfflineModel()),
  ]);
  await plugin.close();
  const roots = events.filter(
    (event) => event.kind === 'run' && event.phase === 'started',
  );
  assert.equal(roots.length, 2);
  assert.notEqual(roots[0]?.runId, roots[1]?.runId);
  const runIds = new Set(roots.map((event) => event.runId));
  assert.ok(events.every((event) => runIds.has(event.runId)));
});
