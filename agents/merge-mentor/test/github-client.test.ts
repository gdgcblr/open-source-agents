import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { GitHubClient } from '../src/github/client.js';

const realFetch = globalThis.fetch;
/** Built at runtime so no token-shaped literal sits in the source. */
const fakeToken = (word: string) => ['ghp', word, '0'.repeat(24)].join('_');
afterEach(() => {
  globalThis.fetch = realFetch;
});

interface Seen {
  url: string;
  method?: string;
  headers: Record<string, string>;
}

/** Replaces fetch with a scripted sequence of responses and records every request. */
function scriptFetch(responses: Response[]): Seen[] {
  const seen: Seen[] = [];
  let i = 0;
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    seen.push({ url: String(input), method: init?.method, headers: { ...(init?.headers as Record<string, string>) } });
    return responses[Math.min(i++, responses.length - 1)];
  }) as typeof fetch;
  return seen;
}

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });

test('only sends GET requests to api.github.com, with the token in a header (never the URL)', async () => {
  const seen = scriptFetch([json({ ok: true })]);
  const gh = new GitHubClient(fakeToken('example'), 'live');
  await gh.getJson('/repos/a/b', { per_page: 5 });
  assert.equal(seen.length, 1);
  assert.equal(seen[0].method, 'GET');
  assert.ok(seen[0].url.startsWith('https://api.github.com/repos/a/b'));
  assert.ok(!seen[0].url.includes(fakeToken('example')), 'token must not appear in the URL');
  assert.match(seen[0].headers.Authorization, /^Bearer /);
});

test('refuses any other host, including look-alikes', async () => {
  const seen = scriptFetch([json({})]);
  const gh = new GitHubClient(undefined, 'live');
  for (const target of ['https://evil.example/x', 'https://api.github.com.evil.example/x', 'http://api.github.com/x']) {
    await assert.rejects(gh.getJson(target), /Blocked request/);
  }
  assert.equal(seen.length, 0, 'no request may leave the machine');
});

test('secondary rate limit: waits as asked, retries once, then succeeds', async () => {
  const seen = scriptFetch([
    json({ message: 'You have exceeded a secondary rate limit.' }, 403, { 'retry-after': '7' }),
    json({ items: [1, 2, 3] }),
  ]);
  const waits: number[] = [];
  const notes: string[] = [];
  const gh = new GitHubClient('t', 'live', undefined, async (ms) => void waits.push(ms));
  gh.onWait = (m) => notes.push(m);
  const data = await gh.getJson<{ items: number[] }>('/search/issues', { q: 'x' });
  assert.deepEqual(data.items, [1, 2, 3]);
  assert.deepEqual(waits, [7000]);
  assert.equal(seen.length, 2);
  assert.match(notes[0], /slow down; waiting 7s/);
});

test('secondary rate limit twice in a row: stops with a clear message instead of looping', async () => {
  const seen = scriptFetch([json({ message: 'secondary rate limit' }, 403, { 'retry-after': '5' })]);
  const gh = new GitHubClient('t', 'live', undefined, async () => {});
  await assert.rejects(gh.getJson('/search/issues'), /rate limiting requests\. Wait about 5 seconds/);
  assert.equal(seen.length, 2, 'exactly one retry');
});

test('a very long retry-after is not waited out (the user is told instead)', async () => {
  const waits: number[] = [];
  scriptFetch([json({ message: 'secondary rate limit' }, 403, { 'retry-after': '3600' })]);
  const gh = new GitHubClient('t', 'live', undefined, async (ms) => void waits.push(ms));
  await assert.rejects(gh.getJson('/x'), /Wait about 3600 seconds/);
  assert.deepEqual(waits, []);
});

test('primary rate limit exhausted: no retry, and the message points at GITHUB_TOKEN when there is none', async () => {
  const seen = scriptFetch([json({ message: 'API rate limit exceeded' }, 403, { 'x-ratelimit-remaining': '0' })]);
  await assert.rejects(new GitHubClient(undefined, 'live').getJson('/x'), /rate limit reached\. Add GITHUB_TOKEN/);
  assert.equal(seen.length, 1);
  await assert.rejects(new GitHubClient('t', 'live').getJson('/x'), (e: Error) => /rate limit reached\.$/.test(e.message));
});

test('error messages never contain the token and keep the GitHub body short', async () => {
  scriptFetch([new Response('x'.repeat(5000), { status: 500 })]);
  const gh = new GitHubClient(fakeToken('secret'), 'live');
  await assert.rejects(gh.getJson('/boom'), (e: Error) => {
    assert.ok(!e.message.includes(fakeToken('secret')));
    assert.ok(e.message.length < 400);
    return true;
  });
});

test('replay mode never touches the network and explains what is missing', async () => {
  const seen = scriptFetch([json({})]);
  const gh = new GitHubClient(undefined, 'replay', { recordedAt: new Date().toISOString(), github: { '/repos/a/b': { name: 'b' } }, gemini: {} });
  assert.deepEqual(await gh.getJson('/repos/a/b'), { name: 'b' });
  await assert.rejects(gh.getJson('/repos/other/thing'), /Demo mode only has recorded data/);
  assert.equal(seen.length, 0);
});
