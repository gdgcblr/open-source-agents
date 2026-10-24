import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { GitHubClient, assertDemoSupports, loadFixture } from '../src/github.js';
import { findRepos } from '../src/finder.js';
import { explainIssue, rankIssues } from '../src/pipeline.js';

/** End-to-end run of the real pipeline on the recorded demo: no network, no API keys. */
const fixture = loadFixture(fileURLToPath(new URL('../fixtures/demo.json', import.meta.url)));
const now = new Date(fixture.recordedAt).getTime();
const gh = new GitHubClient(undefined, 'replay', fixture);

test('demo: project search returns the recorded TypeScript projects', async () => {
  const repos = await findRepos(gh, 'typescript', 'beginner', now);
  const names = repos.map((r) => r.full_name);
  for (const expected of fixture.meta!.repos!) assert.ok(names.includes(expected), expected);
});

test('demo: one project is scored end to end (claim check, Merge Chance, difficulty, ranking)', async () => {
  const repos = await findRepos(gh, 'typescript', 'beginner', now);
  const dexie = repos.find((r) => r.full_name === 'dexie/Dexie.js')!;
  const { rows, hiddenTaken } = await rankIssues({
    gh,
    repos: [dexie],
    language: 'typescript',
    level: 'beginner',
    limit: 20,
    now,
    recordedRatings: fixture.gemini.difficulty as Record<string, { difficulty: number; reason: string }>,
  });
  assert.equal(hiddenTaken, 0);
  assert.equal(rows.length, 5);
  assert.ok(rows.every((r) => r.score.status === 'Available'));
  assert.ok(rows.every((r) => r.difficulty !== undefined), 'every issue has a recorded difficulty');
  assert.deepEqual(rows.map((r) => r.score.score), [...rows.map((r) => r.score.score)].sort((a, b) => b - a), 'ranked best first');
  assert.equal(rows[0].issue.number, 1032);
});

test('demo: the recorded explanation has all 8 sections and passing automatic checks', async () => {
  const repos = await findRepos(gh, 'typescript', 'beginner', now);
  const dexie = repos.find((r) => r.full_name === 'dexie/Dexie.js')!;
  const answer = await explainIssue({ gh, repo: dexie, issue: { number: 1032 } as never, recordedAnswer: String(fixture.gemini.mentor) });
  for (const n of [1, 2, 3, 4, 5, 6, 7, 8]) assert.match(answer, new RegExp(`^## ${n}\\. `, 'm'));
  assert.match(answer, /^## Automatic checks/m);
  assert.doesNotMatch(answer, /⚠️/, 'the recorded demo answer should have no warnings');
});

test('demo: other languages and levels are refused with a clear message', () => {
  assert.throws(() => assertDemoSupports(fixture, 'python', 'beginner'), /only has recorded data for typescript/);
  assert.throws(() => assertDemoSupports(fixture, 'typescript', 'advanced'), /only has recorded data/);
  assert.doesNotThrow(() => assertDemoSupports(fixture, 'typescript', 'beginner'));
});

test('demo data holds no secrets', () => {
  const raw = JSON.stringify(fixture);
  assert.doesNotMatch(raw, /ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}|AIza[0-9A-Za-z_-]{30}|AQ\.Ab8|sk-[A-Za-z0-9_-]{20}/);
});
