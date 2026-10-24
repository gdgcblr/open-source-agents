import { test } from 'node:test';
import assert from 'node:assert/strict';
import { explainMergeChance, scoreMergeChance } from '../src/github/signals.js';
import type { ClaimResult, RepoHealth } from '../src/types.js';

const NOW = new Date('2026-10-24T00:00:00Z').getTime();
const daysAgo = (d: number) => new Date(NOW - d * 86_400_000).toISOString();
const free: ClaimResult = { status: 'Available' };
const sum = (parts: { points: number }[]) => parts.reduce((s, p) => s + p.points, 0);

const healthy: RepoHealth = { closedPRs: 50, mergedPRs: 40, outsideMerged: 30, medianDaysToMerge: 2 };

test('the five signal lines add up to the total (and the notes quote the real numbers)', () => {
  const { total, parts } = explainMergeChance(healthy, daysAgo(2), 1, free, NOW);
  assert.equal(parts.length, 5);
  assert.equal(Math.round(sum(parts)), total);
  const byLabel = Object.fromEntries(parts.map((p) => [p.label, p]));
  assert.match(byLabel['Outside contributors get merged'].note, /30 of 40 recent merged PRs/);
  assert.match(byLabel['Most PRs get merged'].note, /40 of 50 recently closed PRs/);
  assert.match(byLabel['PRs merge quickly'].note, /median 2 days/);
  assert.match(byLabel['The project is active'].note, /last push 2 days ago/);
  assert.match(byLabel['The issue is quiet'].note, /1 comment so far/);
});

test('no line can earn more than its maximum, and no line is negative for a free issue', () => {
  for (const comments of [0, 5, 20]) {
    for (const push of [1, 20, 300]) {
      const { parts } = explainMergeChance(healthy, daysAgo(push), comments, free, NOW);
      for (const p of parts) {
        assert.ok(p.points >= 0 && p.points <= p.max, `${p.label}: ${p.points}/${p.max}`);
      }
    }
  }
});

test('a Taken issue gets a visible "capped" line so the total still adds up', () => {
  const { total, parts } = explainMergeChance(healthy, daysAgo(1), 0, { status: 'Taken', reason: 'PR #5 open' }, NOW);
  assert.equal(total, 15);
  const cap = parts.at(-1)!;
  assert.match(cap.label, /Capped/);
  assert.ok(cap.points < 0);
  assert.match(cap.note, /PR #5 open/);
  assert.equal(Math.round(sum(parts)), 15);
});

test('a Claimed issue shows the penalty as its own line', () => {
  const perfect: RepoHealth = { closedPRs: 50, mergedPRs: 50, outsideMerged: 50, medianDaysToMerge: 1 };
  const { total, parts } = explainMergeChance(perfect, daysAgo(1), 0, { status: 'Claimed', reason: '@sam asked 2d ago' }, NOW);
  assert.equal(total, 70);
  assert.deepEqual(parts.at(-1), { label: 'Recently claimed', points: -30, max: 0, note: '@sam asked 2d ago' });
});

test('a project with no history says so instead of inventing numbers', () => {
  const { total, parts } = explainMergeChance({ closedPRs: 0, mergedPRs: 0, outsideMerged: 0, medianDaysToMerge: null }, daysAgo(400), 30, free, NOW);
  assert.equal(total, 0);
  assert.match(parts[0].note, /no recent merged PRs/);
  assert.match(parts[1].note, /no recently closed PRs/);
  assert.match(parts[2].note, /no merge times/);
});

test('scoreMergeChance is exactly the total from explainMergeChance (one source of truth)', () => {
  const statuses: ClaimResult[] = [free, { status: 'Claimed', reason: 'x' }, { status: 'Taken', reason: 'y' }, { status: 'Fixed', reason: 'z' }];
  for (const claim of statuses) {
    for (const comments of [0, 4, 9]) {
      assert.equal(scoreMergeChance(healthy, daysAgo(3), comments, claim, NOW), explainMergeChance(healthy, daysAgo(3), comments, claim, NOW).total);
    }
  }
});
