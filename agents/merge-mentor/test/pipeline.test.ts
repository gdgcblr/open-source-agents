import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rankIssues } from '../src/pipeline.js';
import type { GitHubClient } from '../src/github/client.js';
import type { Repository } from '../src/types.js';

const NOW = new Date('2026-10-24T00:00:00Z').getTime();
const iso = (days: number) => new Date(NOW - days * 86_400_000).toISOString();

const repo = { full_name: 'o/r', stargazers_count: 1000, pushed_at: iso(1), default_branch: 'main', language: 'TypeScript' } as Repository;
const issue = (number: number) => ({
  number, title: `Issue ${number}`, html_url: `https://github.com/o/r/issues/${number}`, repository_url: 'https://api.github.com/repos/o/r',
  body: 'body', comments: 0, created_at: iso(20), updated_at: iso(2), labels: [{ name: 'good first issue' }],
});
const crossRef = (state: string, merged: string | null) => ({ event: 'cross-referenced', source: { issue: { number: 99, state, pull_request: { merged_at: merged }, repository: { full_name: 'o/r' } } } });

/** GitHub stand-in: issue 1 is free, issue 2 has an open PR, issue 3 was already fixed by a merged PR. */
function fakeGitHub(): { gh: GitHubClient; calls: string[]; maxInFlight: () => number } {
  const calls: string[] = [];
  let inFlight = 0;
  let peak = 0;
  const gh = {
    async getJson(path: string) {
      calls.push(path);
      inFlight++;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight--;
      if (path === '/search/issues') return { items: [issue(1), issue(2), issue(3)] };
      if (path.endsWith('/pulls')) return [];
      if (path.endsWith('/issues/2/timeline')) return [crossRef('open', null)];
      if (path.endsWith('/issues/3/timeline')) return [crossRef('closed', iso(5))];
      if (path.endsWith('/timeline')) return [];
      throw new Error(`unexpected request ${path}`);
    },
  } as unknown as GitHubClient;
  return { gh, calls, maxInFlight: () => peak };
}

const base = { repos: [repo], language: 'typescript', level: 'beginner' as const, limit: 20, now: NOW };

test('rankIssues hides issues with an open PR and issues already fixed by a merged PR', async () => {
  const { gh } = fakeGitHub();
  const { rows, hiddenTaken } = await rankIssues({ ...base, gh });
  assert.deepEqual(rows.map((r) => r.issue.number), [1]);
  assert.equal(hiddenTaken, 2);
  assert.equal(rows[0].score.status, 'Available');
});

test('rankIssues can show everything, labelled with the right status', async () => {
  const { gh } = fakeGitHub();
  const { rows, hiddenTaken } = await rankIssues({ ...base, gh, hideTaken: false });
  assert.equal(hiddenTaken, 0);
  const status = Object.fromEntries(rows.map((r) => [r.issue.number, r.score.status]));
  assert.deepEqual(status, { 1: 'Available', 2: 'Taken', 3: 'Fixed' });
});

test('rankIssues never has more than 4 GitHub requests in flight (stays clear of the secondary rate limit)', async () => {
  const { gh, maxInFlight } = fakeGitHub();
  await rankIssues({ ...base, gh });
  assert.ok(maxInFlight() <= 4, `peak concurrency was ${maxInFlight()}`);
});

test('rankIssues asks Gemini nothing when no issue is left to rate', async () => {
  const { gh } = fakeGitHub();
  let asked = 0;
  const gemini = { generate: async () => void asked++ } as never;
  // Only issues 2 and 3 are returned this time, and both are hidden.
  (gh as unknown as { getJson: (p: string) => Promise<unknown> }).getJson = async (path: string) => {
    if (path === '/search/issues') return { items: [issue(2), issue(3)] };
    if (path.endsWith('/pulls')) return [];
    if (path.endsWith('/issues/2/timeline')) return [crossRef('open', null)];
    return [crossRef('closed', iso(5))];
  };
  const { rows } = await rankIssues({ ...base, gh, gemini });
  assert.equal(rows.length, 0);
  assert.equal(asked, 0, 'no Gemini quota is spent on hidden issues');
});
