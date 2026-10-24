import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { FIXTURE_FILE, PROJECT_ROOT, isValidLevel, loadConfig, normalizeLanguage } from '../src/config.js';
import { DEFAULT_MODEL, LEVELS, LEVEL_PROFILES, MERGE_CHANCE, REPO_REF } from '../src/constants.js';

test('normalizeLanguage maps nicknames to GitHub language names and trims', () => {
  assert.equal(normalizeLanguage(' TS '), 'typescript');
  assert.equal(normalizeLanguage('JS'), 'javascript');
  assert.equal(normalizeLanguage('GoLang'), 'go');
  assert.equal(normalizeLanguage('py'), 'python');
  assert.equal(normalizeLanguage('csharp'), 'c#');
  assert.equal(normalizeLanguage('Zig'), 'zig');
});

test('isValidLevel accepts exactly the three levels', () => {
  assert.deepEqual(LEVELS, ['beginner', 'intermediate', 'advanced']);
  for (const level of LEVELS) assert.ok(isValidLevel(level));
  for (const bad of ['', 'expert', 'Beginner', 'god']) assert.ok(!isValidLevel(bad), bad);
});

test('loadConfig reads keys from the environment; empty values mean "not set"', () => {
  const saved = { ...process.env };
  try {
    process.env.GEMINI_API_KEY = 'gem-test';
    process.env.GITHUB_TOKEN = 'gh-test';
    process.env.MODEL_NAME = 'my-model';
    assert.deepEqual(loadConfig(), { geminiApiKey: 'gem-test', githubToken: 'gh-test', modelName: 'my-model' });

    process.env.GEMINI_API_KEY = '';
    process.env.GITHUB_TOKEN = '';
    process.env.MODEL_NAME = '';
    assert.deepEqual(loadConfig(), { geminiApiKey: undefined, githubToken: undefined, modelName: DEFAULT_MODEL });
  } finally {
    process.env = saved;
  }
});

test('levels are ordered: more advanced levels target harder issues and different labels', () => {
  const [b, i, a] = LEVELS.map((l) => LEVEL_PROFILES[l]);
  assert.ok(b.targetDifficulty < i.targetDifficulty && i.targetDifficulty < a.targetDifficulty);
  assert.ok(b.labels.includes('good first issue'));
  assert.ok(b.labels.every((l) => i.labels.includes(l)), 'intermediate includes every beginner label');
  assert.ok(i.labels.includes('help wanted'));
  assert.ok(!a.labels.includes('good first issue'), 'advanced is not about beginner labels');
});

test('Merge Chance weights add up to 100 and the bands are sensible', () => {
  const W = MERGE_CHANCE;
  const best = (bands: readonly { points: number }[]) => Math.max(...bands.map((b) => b.points));
  assert.equal(W.outsideContributorPoints + W.mergeRatePoints + best(W.mergeSpeedBands) + best(W.repoActivityBands) + best(W.quietIssueBands), 100);
  assert.ok(W.bandHigh > W.bandMedium && W.bandMedium > 0);
  for (const bands of [W.mergeSpeedBands, W.repoActivityBands, W.quietIssueBands]) {
    const limits = bands.map((b) => ('maxDays' in b ? b.maxDays : b.maxComments));
    assert.deepEqual(limits, [...limits].sort((x, y) => x - y), 'bands must run from tightest to loosest');
    const points = bands.map((b) => b.points);
    assert.deepEqual(points, [...points].sort((x, y) => y - x), 'looser bands must never earn more');
  }
  assert.ok(W.takenCap < W.bandMedium, 'a taken issue can never look promising');
});

test('paths are anchored at the project root and the demo recording exists', () => {
  assert.ok(existsSync(`${PROJECT_ROOT}/package.json`));
  assert.ok(FIXTURE_FILE.endsWith('fixtures/demo.json'));
  assert.ok(existsSync(FIXTURE_FILE));
});

test('REPO_REF accepts normal names with dots, dashes and underscores', () => {
  for (const ok of ['dexie/Dexie.js', 'a-b/c_d', 'microsoft/TypeScript', 'x/y.z']) assert.ok(REPO_REF.test(ok), ok);
});
