import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeRepoHealth, detectClaim, isClaimComment, scoreBand, scoreMergeChance } from '../src/github/signals.js';

const NOW = new Date('2026-10-24T00:00:00Z').getTime();
const daysAgo = (d: number) => new Date(NOW - d * 86_400_000).toISOString();

test('isClaimComment recognises common claim phrases', () => {
  for (const text of ['Can I work on this?', "I'd like to take this", 'Please assign me', "I'll fix this", 'working on it']) {
    assert.ok(isClaimComment(text), text);
  }
  for (const text of ['This is broken on Windows', 'Thanks for the report']) assert.ok(!isClaimComment(text), text);
});

test('detectClaim: open linked PR means Taken', () => {
  const timeline = [{ event: 'cross-referenced', source: { issue: { number: 7, state: 'open', pull_request: {}, repository: { full_name: 'a/b' } } } }];
  assert.deepEqual(detectClaim(timeline, NOW, 'a/b'), { status: 'Taken', reason: 'PR #7 open' });
});

test('detectClaim: PR from another repository does not count', () => {
  const timeline = [{ event: 'cross-referenced', source: { issue: { number: 1, state: 'open', pull_request: {}, repository: { full_name: 'other/repo' } } } }];
  assert.equal(detectClaim(timeline, NOW, 'a/b').status, 'Available');
});

test('detectClaim: closed PR does not count', () => {
  const timeline = [{ event: 'cross-referenced', source: { issue: { number: 7, state: 'closed', pull_request: {}, repository: { full_name: 'a/b' } } } }];
  assert.equal(detectClaim(timeline, NOW, 'a/b').status, 'Available');
});

test('detectClaim: recent claim means Claimed, old or bot claims are ignored', () => {
  const claim = (user: string, days: number, type = 'User') => [{ event: 'commented', body: 'Can I work on this?', created_at: daysAgo(days), user: { login: user, type } }];
  assert.equal(detectClaim(claim('sam', 2), NOW, 'a/b').status, 'Claimed');
  assert.equal(detectClaim(claim('sam', 45), NOW, 'a/b').status, 'Available');
  assert.equal(detectClaim(claim('helper[bot]', 1, 'Bot'), NOW, 'a/b').status, 'Available');
});

test('computeRepoHealth counts outside merges and median merge time', () => {
  const pr = (assoc: string, created: number, merged: number | null) => ({
    author_association: assoc,
    created_at: daysAgo(created),
    merged_at: merged === null ? null : daysAgo(merged),
  });
  const health = computeRepoHealth([pr('NONE', 5, 4), pr('OWNER', 10, 6), pr('FIRST_TIME_CONTRIBUTOR', 3, 1), pr('NONE', 2, null)]);
  assert.equal(health.closedPRs, 4);
  assert.equal(health.mergedPRs, 3);
  assert.equal(health.outsideMerged, 2);
  assert.equal(health.medianDaysToMerge, 2);
});

test('scoreMergeChance rewards healthy repos and caps Taken / penalises Claimed', () => {
  const healthy = { closedPRs: 50, mergedPRs: 50, outsideMerged: 50, medianDaysToMerge: 1 };
  const available = { status: 'Available' as const };
  assert.equal(scoreMergeChance(healthy, daysAgo(1), 0, available, NOW), 100);
  assert.equal(scoreMergeChance(healthy, daysAgo(1), 0, { status: 'Taken', reason: 'x' }, NOW), 15);
  assert.equal(scoreMergeChance(healthy, daysAgo(1), 0, { status: 'Claimed', reason: 'x' }, NOW), 70);
  const dead = { closedPRs: 0, mergedPRs: 0, outsideMerged: 0, medianDaysToMerge: null };
  assert.equal(scoreMergeChance(dead, daysAgo(400), 20, available, NOW), 0);
});

test('scoreBand thresholds', () => {
  assert.deepEqual([scoreBand(70), scoreBand(45), scoreBand(44)], ['High', 'Medium', 'Low']);
});

test('computeRepoHealth ignores bot PRs (dependabot must not look like outside contributors)', () => {
  const bot = { author_association: 'NONE', created_at: daysAgo(2), merged_at: daysAgo(1), user: { login: 'dependabot[bot]', type: 'Bot' } };
  const human = { author_association: 'FIRST_TIME_CONTRIBUTOR', created_at: daysAgo(4), merged_at: daysAgo(2), user: { login: 'sam', type: 'User' } };
  const health = computeRepoHealth([bot, bot, bot, human]);
  assert.equal(health.closedPRs, 1);
  assert.equal(health.mergedPRs, 1);
  assert.equal(health.outsideMerged, 1);
});

// ---- "probably already fixed": a merged PR in the same repo references an issue that is still open ----

const xref = (state: string, merged: string | null, repo = 'a/b', number = 11) => ({
  event: 'cross-referenced',
  source: { issue: { number, state, pull_request: { merged_at: merged }, repository: { full_name: repo } } },
});

test('detectClaim: a merged PR that references the open issue means probably Fixed', () => {
  const result = detectClaim([xref('closed', daysAgo(3))], NOW, 'a/b');
  assert.deepEqual(result, { status: 'Fixed', reason: 'PR #11 already merged' });
});

test('detectClaim: an open PR still wins over a merged one (someone is still working on it)', () => {
  assert.equal(detectClaim([xref('closed', daysAgo(3), 'a/b', 11), xref('open', null, 'a/b', 12)], NOW, 'a/b').status, 'Taken');
  assert.equal(detectClaim([xref('open', null, 'a/b', 12), xref('closed', daysAgo(3), 'a/b', 11)], NOW, 'a/b').status, 'Taken');
});

test('detectClaim: Fixed beats a claim comment, because a fixed issue needs no one', () => {
  const comment = { event: 'commented', body: 'Can I work on this?', created_at: daysAgo(1), user: { login: 'sam', type: 'User' } };
  assert.equal(detectClaim([comment, xref('closed', daysAgo(3))], NOW, 'a/b').status, 'Fixed');
});

test('detectClaim: a PR closed without merging, or merged in another repo, does not make it Fixed', () => {
  assert.equal(detectClaim([xref('closed', null)], NOW, 'a/b').status, 'Available');
  assert.equal(detectClaim([xref('closed', daysAgo(3), 'other/repo')], NOW, 'a/b').status, 'Available');
});

test('scoreMergeChance caps a Fixed issue like a Taken one', () => {
  const healthy = { closedPRs: 50, mergedPRs: 50, outsideMerged: 50, medianDaysToMerge: 1 };
  assert.equal(scoreMergeChance(healthy, daysAgo(1), 0, { status: 'Fixed', reason: 'x' }, NOW), 15);
});
