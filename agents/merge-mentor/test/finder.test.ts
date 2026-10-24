import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchIssue, findIssues, findRepos, parseIssueRef } from '../src/github/finder.js';
import { ISSUE_PAGE_SIZE, ISSUES_PER_PROJECT_MIXED, ISSUES_PER_PROJECT_OPEN, MAX_STARS, MIN_STARS } from '../src/constants.js';
import type { GitHubClient } from '../src/github/client.js';
import type { Repository } from '../src/types.js';

const NOW = new Date('2026-10-24T00:00:00Z').getTime();

interface Call {
  path: string;
  params: Record<string, string | number>;
}
function fakeGh(responses: Record<string, unknown>): { gh: GitHubClient; calls: Call[] } {
  const calls: Call[] = [];
  const gh = {
    async getJson(path: string, params: Record<string, string | number> = {}) {
      calls.push({ path, params });
      return responses[path] ?? {};
    },
  } as unknown as GitHubClient;
  return { gh, calls };
}

const repo = (name: string) => ({ full_name: name }) as Repository;
const item = (number: number, repoName: string, extra: object = {}) => ({
  number, title: `Issue ${number}`, html_url: `https://github.com/${repoName}/issues/${number}`, repository_url: `https://api.github.com/repos/${repoName}`,
  body: 'b', comments: 0, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z', labels: [], ...extra,
});

test('findRepos searches mid-size, recently active, unarchived repos in the language, best-starred first', async () => {
  const { gh, calls } = fakeGh({ '/search/repositories': { items: [{ full_name: 'a/b' }] } });
  const repos = await findRepos(gh, 'typescript', 'beginner', NOW, 2);
  assert.deepEqual(repos.map((r) => r.full_name), ['a/b']);
  const { path, params } = calls[0];
  assert.equal(path, '/search/repositories');
  const q = String(params.q);
  for (const part of ['language:typescript', `stars:${MIN_STARS}..${MAX_STARS}`, 'archived:false', 'pushed:>2026-09-24', 'good-first-issues:>=2']) assert.ok(q.includes(part), part);
  assert.equal(params.sort, 'stars');
  assert.equal(params.order, 'desc');
  assert.equal(params.page, 2);
});

test('advanced level looks for help-wanted projects instead of good-first-issue ones', async () => {
  const { gh, calls } = fakeGh({});
  await findRepos(gh, 'go', 'advanced', NOW);
  assert.ok(String(calls[0].params.q).includes('help-wanted-issues:>=2'));
  assert.ok(!String(calls[0].params.q).includes('good-first-issues'));
});

test('findIssues asks only for open, unassigned issues without a linked PR, quietest first', async () => {
  const { gh, calls } = fakeGh({ '/search/issues': { items: [] } });
  await findIssues(gh, [repo('o/a'), repo('o/b')], 'beginner', 20, 3);
  const { params } = calls[0];
  const q = String(params.q);
  for (const part of ['is:issue', 'is:open', 'no:assignee', '-linked:pr', 'repo:o/a', 'repo:o/b', '"good first issue"']) assert.ok(q.includes(part), part);
  assert.equal(params.sort, 'comments');
  assert.equal(params.order, 'asc');
  assert.equal(params.per_page, ISSUE_PAGE_SIZE);
  assert.equal(params.page, 3);
});

test('advanced issues use help-wanted labels only', async () => {
  const { gh, calls } = fakeGh({});
  await findIssues(gh, [repo('o/a')], 'advanced', 20);
  const q = String(calls[0].params.q);
  assert.ok(q.includes('"help wanted"'));
  assert.ok(!q.includes('good first issue'));
});

test('across several projects each shows at most a few issues; one opened project shows many', async () => {
  const many = Array.from({ length: 25 }, (_, i) => item(i + 1, 'o/a'));
  const mixed = await findIssues(fakeGh({ '/search/issues': { items: many } }).gh, [repo('o/a'), repo('o/b')], 'beginner', 50);
  assert.equal(mixed.issues.length, ISSUES_PER_PROJECT_MIXED);
  const single = await findIssues(fakeGh({ '/search/issues': { items: many } }).gh, [repo('o/a')], 'beginner', 50);
  assert.equal(single.issues.length, ISSUES_PER_PROJECT_OPEN);
});

test('the limit caps how many candidates come back', async () => {
  const items = Array.from({ length: 10 }, (_, i) => item(i + 1, 'o/a'));
  const { issues } = await findIssues(fakeGh({ '/search/issues': { items } }).gh, [repo('o/a')], 'beginner', 4);
  assert.equal(issues.length, 4);
});

test('pull requests and issues from repos we did not ask about are dropped', async () => {
  const items = [item(1, 'o/a'), item(2, 'o/a', { pull_request: { url: 'x' } }), item(3, 'evil/other'), item(4, 'O/A')];
  const { issues } = await findIssues(fakeGh({ '/search/issues': { items } }).gh, [repo('o/a')], 'beginner', 20);
  assert.deepEqual(issues.map((i) => i.number), [1, 4]);
  assert.equal(issues[0].repo_full_name, 'o/a');
});

test('hasMore is true only when a full page came back', async () => {
  const full = Array.from({ length: ISSUE_PAGE_SIZE }, (_, i) => item(i + 1, 'o/a'));
  assert.equal((await findIssues(fakeGh({ '/search/issues': { items: full } }).gh, [repo('o/a')], 'beginner', 5)).hasMore, true);
  assert.equal((await findIssues(fakeGh({ '/search/issues': { items: full.slice(0, 5) } }).gh, [repo('o/a')], 'beginner', 5)).hasMore, false);
});

test('no repositories means no search at all', async () => {
  const { gh, calls } = fakeGh({});
  assert.deepEqual(await findIssues(gh, [], 'beginner', 10), { issues: [], hasMore: false });
  assert.equal(calls.length, 0);
});

test('parseIssueRef understands owner/repo#n and issue URLs, and rejects traversal', () => {
  assert.deepEqual(parseIssueRef('dexie/Dexie.js#1032'), { repo: 'dexie/Dexie.js', number: 1032 });
  assert.deepEqual(parseIssueRef('https://github.com/a/b/issues/9'), { repo: 'a/b', number: 9 });
  for (const bad of ['', 'nonsense', '../etc#1', 'a/b#x', 'a/b/c#1']) assert.equal(parseIssueRef(bad), null, bad);
});

test('fetchIssue refuses a pull request passed as an issue', async () => {
  const gh = fakeGh({ '/repos/o/r/issues/5': { number: 5, pull_request: {} } }).gh;
  await assert.rejects(fetchIssue(gh, 'o/r', 5), /is a pull request, not an issue/);
});
