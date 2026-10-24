import { test } from 'node:test';
import assert from 'node:assert/strict';
import { maskSecrets, numberLines, safeRepoPath } from '../src/ai/mentor.js';
import { GitHubClient } from '../src/github/client.js';
import { normalizeLanguage } from '../src/config.js';
import { parseIssueRef } from '../src/github/finder.js';

test('safeRepoPath blocks traversal and normalises slashes', () => {
  assert.equal(safeRepoPath('/src/utils/'), 'src/utils');
  assert.equal(safeRepoPath(''), '');
  assert.throws(() => safeRepoPath('../secrets'));
  assert.throws(() => safeRepoPath('src/../../etc/passwd'));
  assert.throws(() => safeRepoPath('a\\b'));
});

test('numberLines numbers lines and caps at 400', () => {
  const text = Array.from({ length: 1000 }, (_, i) => `line${i + 1}`).join('\n');
  assert.ok(numberLines(text, 3, 4).startsWith('3: line3\n4: line4'));
  const out = numberLines(text, 1, 1000).split('\n');
  assert.equal(out.length, 401); // 400 lines + truncation note
  assert.ok(out[400].includes('showing 1-400'));
});

test('maskSecrets hides token-like strings', () => {
  // Built at runtime so no token-shaped literal sits in the source.
  const github = 'ghp' + '_' + 'x'.repeat(36);
  const google = 'AIza' + 'y'.repeat(35);
  const text = `a ${github} b ${google} c`;
  assert.equal(maskSecrets(text), 'a [REDACTED] b [REDACTED] c');
});

test('GitHubClient only talks to api.github.com', async () => {
  const gh = new GitHubClient(undefined);
  await assert.rejects(gh.getJson('https://evil.example.com/steal'), /Blocked request/);
});

test('normalizeLanguage and parseIssueRef', () => {
  assert.equal(normalizeLanguage(' TS '), 'typescript');
  assert.equal(normalizeLanguage('Python'), 'python');
  assert.deepEqual(parseIssueRef('meteor/meteor#14612'), { repo: 'meteor/meteor', number: 14612 });
  assert.deepEqual(parseIssueRef('https://github.com/a/b/issues/9'), { repo: 'a/b', number: 9 });
  assert.equal(parseIssueRef('nonsense'), null);
});

import { sanitizeSearchQuery } from '../src/ai/mentor.js';
import { REPO_REF } from '../src/constants.js';

test('sanitizeSearchQuery strips qualifiers so code search stays inside the chosen repo', () => {
  assert.equal(sanitizeSearchQuery('password repo:someone/private'), 'password');
  assert.equal(sanitizeSearchQuery('token org:acme user:bob path:/etc'), 'token');
  assert.equal(sanitizeSearchQuery('registerCommand "gemini.diff.accept"'), 'registerCommand gemini.diff.accept');
  assert.equal(sanitizeSearchQuery('repo:a/b'), '');
  assert.equal(sanitizeSearchQuery(undefined), '');
});

test('numberLines copes with model-supplied junk numbers', () => {
  assert.ok(numberLines('a\nb\nc', 'abc', 'xyz').startsWith('1: a\n2: b\n3: c'));
  assert.ok(numberLines('a\nb\nc', '2', undefined).startsWith('2: b'));
  assert.ok(numberLines('a\nb\nc', Infinity, NaN).startsWith('1: a')); // falls back to the start
});

test('REPO_REF accepts owner/name and rejects traversal-looking names', () => {
  for (const ok of ['dexie/Dexie.js', 'vercel/next.js', 'a-b/c_d']) assert.ok(REPO_REF.test(ok), ok);
  for (const bad of ['../etc', 'a/..', './x', 'a/b/c', 'a', 'a/b?x=1', '']) assert.ok(!REPO_REF.test(bad), bad);
});
