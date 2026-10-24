import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import test from 'node:test';
import { createAgentLogger, readLog } from '../src/index.js';

test('reader and CLI inspect an actual JSONL run', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-log-reader-'));
  const logger = await createAgentLogger({ directory });
  await logger.run('task', async () => logger.wrapTool('search', () => 'found')());
  await logger.close();
  assert.ok(logger.filePath);
  const events = await readLog(logger.filePath);
  assert.equal(events.length, 4);
  const { stdout } = await promisify(execFile)(process.execPath, [
    'test-dist/src/cli.js',
    'view',
    logger.filePath,
  ]);
  assert.match(stdout, /tool search completed/);
  assert.match(stdout, /Events: 4/);
});

test('reader rejects malformed schemas and unsafe numeric fields', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-log-invalid-'));
  const filePath = join(directory, 'bad.jsonl');
  await writeFile(filePath, '{"schemaVersion":9}\n');
  await assert.rejects(readLog(filePath));
  await writeFile(filePath, 'not-json\n');
  await assert.rejects(readLog(filePath));
});

test('reader rejects lifecycle fields with incorrect JSON types', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-log-lifecycle-'));
  const filePath = join(directory, 'event.jsonl');
  const event = {
    schemaVersion: 1,
    sequence: 1,
    timestamp: '2026-01-01T00:00:00.000Z',
    runId: '00000000-0000-4000-8000-000000000001',
    spanId: '00000000-0000-4000-8000-000000000002',
    name: 'task',
    kind: 'run',
    phase: 'finished',
    status: 'completed',
  };
  for (const invalid of [
    { kind: ['run'] },
    { phase: ['finished'] },
    { status: ['completed'] },
    { phase: 'started', status: ['completed'] },
    { status: undefined },
  ]) {
    await writeFile(filePath, JSON.stringify({ ...event, ...invalid }) + '\n');
    await assert.rejects(readLog(filePath));
  }
  await writeFile(filePath, JSON.stringify(event) + '\n');
  assert.equal((await readLog(filePath)).length, 1);
});
