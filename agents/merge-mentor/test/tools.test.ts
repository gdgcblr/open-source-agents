import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mentorIssue } from '../src/ai/mentor.js';
import type { GitHubClient } from '../src/github/client.js';
import type { Gemini } from '../src/ai/gemini.js';
import type { Issue } from '../src/types.js';

/** The agent's three read-only tools, exercised through the real agent loop with a scripted model. */
const issue = { number: 1, title: 't', body: 'b', labels: [], html_url: 'u', repo_full_name: 'o/r', comments: 0 } as unknown as Issue;

function repoClient(opts: { files: string[]; truncated?: boolean; contents?: Record<string, string>; token?: boolean; found?: string[] }) {
  const searches: string[] = [];
  const gh = {
    hasToken: opts.token ?? false,
    async getJson(path: string, params: Record<string, string> = {}) {
      if (path.includes('/git/trees/')) return { truncated: opts.truncated ?? false, tree: opts.files.map((p) => ({ path: p, type: 'blob' })) };
      if (path === '/search/code') {
        searches.push(params.q);
        return { items: (opts.found ?? []).map((p) => ({ path: p })) };
      }
      throw new Error(`unexpected ${path}`);
    },
    async getRaw(path: string) {
      const file = decodeURIComponent(path.split('/contents/')[1]);
      if (opts.contents?.[file] === undefined) throw new Error('404 not found');
      return opts.contents[file];
    },
  } as unknown as GitHubClient;
  return { gh, searches };
}

type Call = { name: string; args: Record<string, unknown> };

/** Runs one agent turn that calls the given tools, and returns what the tools handed back to the model. */
async function results(repo: string, client: GitHubClient, calls: Call[]): Promise<string[]> {
  const requests: { contents: { parts: { functionResponse?: { response: { result: string } } }[] }[] }[] = [];
  let turn = 0;
  const gemini = {
    async generate(params: never) {
      requests.push(params);
      turn++;
      return turn === 1
        ? { functionCalls: calls, candidates: [{ content: { role: 'model', parts: calls.map((c) => ({ functionCall: c })) } }] }
        : { text: 'final', candidates: [{ content: { role: 'model', parts: [{ text: 'final' }] } }] };
    },
  } as unknown as Gemini;
  await mentorIssue({ gemini, ctx: { gh: client, repo, branch: 'main' }, issue, comments: [] });
  // The loop reuses one list, so later turns (e.g. a repair round) are appended after the tool results.
  const toolTurn = requests[1].contents.find((c) => c.parts.some((p) => p.functionResponse));
  return toolTurn!.parts.map((p) => p.functionResponse!.response.result);
}

const lines = (n: number) => Array.from({ length: n }, (_, i) => `line ${i + 1}`).join('\n');

test('list_files shows only the immediate children of a folder', async () => {
  const { gh } = repoClient({ files: ['README.md', 'src/a.ts', 'src/util/b.ts', 'src/util/c.ts', 'docs/x.md'] });
  const [root, src] = await results('o/tree1', gh, [{ name: 'list_files', args: { prefix: '' } }, { name: 'list_files', args: { prefix: 'src' } }]);
  assert.deepEqual(JSON.parse(root), ['README.md', 'docs/', 'src/']);
  assert.deepEqual(JSON.parse(src), ['a.ts', 'util/']);
});

test('list_files tells the model when GitHub cut the file list off', async () => {
  const { gh } = repoClient({ files: ['a.ts'], truncated: true });
  const [out] = await results('o/tree2', gh, [{ name: 'list_files', args: { prefix: '' } }]);
  assert.match(out, /truncated the file list/);
});

test('search_code is unavailable without a GitHub token', async () => {
  const { gh, searches } = repoClient({ files: ['a.ts'], token: false });
  const [out] = await results('o/search1', gh, [{ name: 'search_code', args: { query: 'foo' } }]);
  assert.match(out, /GITHUB_TOKEN is not set/);
  assert.equal(searches.length, 0);
});

test('search_code strips qualifiers so it can only ever search the chosen repo', async () => {
  const { gh, searches } = repoClient({ files: ['a.ts'], token: true, found: ['src/a.ts', 'src/b.ts'] });
  const [out, empty] = await results('o/search2', gh, [
    { name: 'search_code', args: { query: 'password repo:evil/other org:acme path:/etc' } },
    { name: 'search_code', args: { query: 'repo:evil/other' } },
  ]);
  assert.deepEqual(searches, ['password repo:o/search2']);
  assert.deepEqual(JSON.parse(out), ['src/a.ts', 'src/b.ts']);
  assert.match(empty, /give search words, not search qualifiers/);
});

test('read_file returns numbered lines, at most 400, and says how much was left out', async () => {
  const { gh } = repoClient({ files: ['big.ts'], contents: { 'big.ts': lines(1000) } });
  const [first, middle] = await results('o/read1', gh, [
    { name: 'read_file', args: { path: 'big.ts' } },
    { name: 'read_file', args: { path: 'big.ts', start_line: 500, end_line: 503 } },
  ]);
  const shown = first.split('\n');
  assert.equal(shown[0], '1: line 1');
  assert.equal(shown[399], '400: line 400');
  assert.match(shown[400], /file has 1000 lines; showing 1-400/);
  assert.equal(middle.split('\n')[0], '500: line 500');
  assert.ok(middle.startsWith('500: line 500\n501: line 501\n502: line 502\n503: line 503'));
});

test('read_file reports a missing file as an error result, not a crash', async () => {
  const { gh } = repoClient({ files: [], contents: {} });
  const [out] = await results('o/read2', gh, [{ name: 'read_file', args: { path: 'nope.ts' } }]);
  assert.match(out, /^Error: 404 not found/);
});

test('tool calls beyond the step limit are refused', async () => {
  const { gh } = repoClient({ files: ['a.ts'], contents: { 'a.ts': 'x' } });
  const calls: Call[] = Array.from({ length: 10 }, () => ({ name: 'read_file', args: { path: 'a.ts' } }));
  const out = await results('o/limit', gh, calls);
  assert.equal(out.filter((r) => r.startsWith('1: x')).length, 8);
  assert.equal(out.filter((r) => /Tool step limit reached/.test(r)).length, 2);
});
