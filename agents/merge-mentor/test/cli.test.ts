import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

/** Runs the real CLI as a child process. Keys are blanked so nothing can reach the network. */
const ROOT = fileURLToPath(new URL('..', import.meta.url));
function cli(...args: string[]) {
  const run = spawnSync(process.execPath, ['--import', 'tsx', 'src/cli.ts', ...args], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 60_000,
    env: { ...process.env, GEMINI_API_KEY: '', GITHUB_TOKEN: '', NO_COLOR: '1' },
  });
  return { code: run.status, out: run.stdout, err: run.stderr };
}

test('--help explains usage and the options', () => {
  const { code, out } = cli('--help');
  assert.equal(code, 0);
  for (const text of ['Usage:', '--lang', '--level', '--repo', '--show-taken', '--demo', 'default 10']) assert.ok(out.includes(text), text);
});

test('a bad level is refused with the valid choices', () => {
  const { code, err } = cli('--level', 'god', '--lang', 'go');
  assert.equal(code, 1);
  assert.match(err, /--level must be one of: beginner, intermediate, advanced/);
});

test('running without a language or issue says what to do', () => {
  const { code, err } = cli();
  assert.equal(code, 1);
  assert.match(err, /Tell me your language/);
});

test('a malformed --issue or --repo is rejected before any request is made', () => {
  assert.match(cli('--issue', 'nonsense').err, /--issue must look like owner\/repo#123/);
  const repo = cli('--demo', '--lang', 'typescript', '--repo', '../etc');
  assert.equal(repo.code, 1);
  assert.match(repo.err, /--repo must look like owner\/name/);
});

test('demo mode refuses anything that was not recorded, with a clear message', () => {
  const { code, err } = cli('--demo', '--lang', 'python', '--level', 'beginner', '--pick', '1');
  assert.equal(code, 1);
  assert.match(err, /Demo mode only has recorded data for typescript at beginner level/);
});

test('demo mode runs the whole flow offline: ranked issues, then the explanation with its checks', () => {
  const { code, out } = cli('--demo', '--lang', 'typescript', '--level', 'beginner', '--pick', '1');
  assert.equal(code, 0, out);
  assert.match(out, /dexie\/Dexie\.js#1032 Improve docs of DBCore/);
  assert.match(out, /94 High/);
  assert.match(out, /## 1\. What the issue is/);
  assert.match(out, /## Automatic checks/);
});

test('picking a number that is not in the list is an error, not a crash', () => {
  const { code, err } = cli('--demo', '--lang', 'typescript', '--level', 'beginner', '--pick', '99');
  assert.equal(code, 1);
  assert.match(err, /Pick a number between 1 and 5/);
});

test('in demo mode, picking an issue without a recording explains how to see it live', () => {
  const { code, out } = cli('--demo', '--lang', 'typescript', '--level', 'beginner', '--pick', '2');
  assert.equal(code, 0);
  assert.match(out, /Demo mode only has a recorded explanation for dexie\/Dexie\.js#1032/);
});
