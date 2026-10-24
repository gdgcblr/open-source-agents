import assert from 'node:assert/strict';
import { mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { createAgentLogger, type LogEvent } from '../src/index.js';
import { runStoryAgent } from '../examples/story-agent.js';
import { readRepositoryContext } from '../examples/repository-context.js';

test('framework-neutral story agent records model usage and its actual word-count tool', async () => {
  const events: LogEvent[] = [];
  const logger = await createAgentLogger({
    captureContent: true,
    sink: {
      write: (event) => {
        events.push(event);
      },
    },
  });
  const result = await runStoryAgent(logger, async (_prompt, span) => {
    span.recordUsage('gemini', {
      usageMetadata: {
        promptTokenCount: 10,
        candidatesTokenCount: 6,
        totalTokenCount: 16,
      },
    });
    return 'A robot found the lost library.';
  });
  assert.equal(result.wordCount, 6);
  assert.equal((await logger.close()).success, true);
  assert.equal(events.length, 6);
  assert.match(JSON.stringify(events), /A robot found/);
  assert.match(JSON.stringify(events), /"totalTokens":16/);
});

test('repository context reads only the selected public files and rejects escaped symlinks', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'agent-context-test-'));
  const root = join(directory, 'repository');
  await mkdir(root);
  await writeFile(join(root, 'README.md'), 'Public project summary');
  await writeFile(join(root, 'package.json'), '{"name":"fixture"}');
  await writeFile(join(root, '.env'), 'SECRET=never-read');
  assert.ok(!(await readRepositoryContext(root)).includes('never-read'));
  const unsafeRoot = join(directory, 'unsafe');
  await mkdir(unsafeRoot);
  await symlink(join(root, '.env'), join(unsafeRoot, 'README.md'));
  await writeFile(join(unsafeRoot, 'package.json'), '{}');
  await assert.rejects(readRepositoryContext(unsafeRoot), /escapes/);
});
