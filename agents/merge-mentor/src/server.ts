#!/usr/bin/env node
import http from 'node:http';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { LEVELS, Level, PROJECT_ROOT, isValidLevel, loadConfig, normalizeLanguage } from './config.js';
import { Fixture, GitHubClient, assertDemoSupports, loadFixture } from './github.js';
import { Issue, Repository, fetchIssue, fetchRepo } from './finder.js';
import { scoreBand } from './signals.js';
import { Gemini } from './gemini.js';
import { issueKey } from './difficulty.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { maskSecrets } from './mentor.js';
import type { Row } from './render.js';

const { values } = parseArgs({
  options: { demo: { type: 'boolean', default: false }, port: { type: 'string' } },
});

const config = loadConfig();
const demo = values.demo!;
const fixture: Fixture | undefined = demo ? loadFixture(path.join(PROJECT_ROOT, 'fixtures', 'demo.json')) : undefined;
const now = fixture ? new Date(fixture.recordedAt).getTime() : undefined;
const gh = new GitHubClient(config.githubToken, demo ? 'replay' : 'live', fixture);
const gemini = !demo && config.geminiApiKey ? new Gemini(config.geminiApiKey, config.modelName) : undefined;
const port = Number(values.port ?? process.env.PORT ?? 3000);

/** Rows from the most recent searches, so opening an issue does not refetch it. */
const known = new Map<string, { issue: Issue; repo: Repository }>();

const PAGE = path.join(PROJECT_ROOT, 'web', 'index.html');
const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:",
};

function json(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...SECURITY_HEADERS });
  res.end(JSON.stringify(body));
}

function toJson(row: Row) {
  const { issue, repo, score, difficulty } = row;
  return {
    key: issueKey(issue),
    repo: repo.full_name,
    stars: repo.stargazers_count,
    number: issue.number,
    title: issue.title,
    url: issue.html_url,
    labels: issue.labels.map((l) => l.name),
    comments: issue.comments,
    status: score.status,
    reason: score.reason ?? null,
    score: score.score,
    band: scoreBand(score.score),
    difficulty: difficulty?.difficulty ?? null,
    difficultyReason: difficulty?.reason ?? null,
    health: score.health,
  };
}

async function handleIssues(url: URL, res: http.ServerResponse): Promise<void> {
  const lang = (url.searchParams.get('lang') ?? '').trim();
  const level = url.searchParams.get('level') ?? 'beginner';
  if (!/^[\w.+#-]{1,30}$/.test(lang)) return json(res, 400, { error: 'Enter a language such as typescript, python or go.' });
  if (!isValidLevel(level)) return json(res, 400, { error: `Level must be one of: ${LEVELS.join(', ')}` });

  const language = normalizeLanguage(lang);
  assertDemoSupports(fixture, language, level);
  const page = Math.max(1, Math.min(5, Math.floor(Number(url.searchParams.get('page'))) || 1));
  if (fixture && page > 1) return json(res, 200, { issues: [], hiddenTaken: 0, page, hasMore: false });
  const { rows, hiddenTaken, hasMore } = await rankIssues({
    gh,
    gemini,
    language,
    level: level as Level,
    limit: 20,
    page,
    now: now ?? Date.now(),
    recordedRatings: fixture ? ((fixture.gemini.difficulty ?? {}) as Record<string, any>) : undefined,
  });
  for (const r of rows) known.set(issueKey(r.issue), { issue: r.issue, repo: r.repo });
  json(res, 200, { issues: rows.map(toJson), hiddenTaken, page, hasMore });
}

function handleExplain(url: URL, req: http.IncomingMessage, res: http.ServerResponse): void {
  const repoName = url.searchParams.get('repo') ?? '';
  const number = Number(url.searchParams.get('number'));
  if (!/^[\w.-]+\/[\w.-]+$/.test(repoName) || !Number.isInteger(number) || number < 1) {
    return json(res, 400, { error: 'Invalid issue reference.' });
  }

  res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', Connection: 'keep-alive', ...SECURITY_HEADERS });
  const send = (event: string, data: unknown) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  let closed = false;
  req.on('close', () => (closed = true));

  (async () => {
    const key = `${repoName}#${number}`;
    let entry = known.get(key);
    if (!entry && !demo) {
      const [repo, issue] = await Promise.all([fetchRepo(gh, repoName), fetchIssue(gh, repoName, number)]);
      entry = { repo, issue };
    }
    if (!entry) throw new Error('Search for issues first, then open one.');

    let recordedAnswer: string | undefined;
    if (fixture) {
      const recordedFor = String(fixture.gemini.mentorFor ?? '');
      recordedAnswer = key === recordedFor
        ? String(fixture.gemini.mentor ?? '')
        : `Demo mode only includes a recorded explanation for **${recordedFor}**. Start the UI without \`--demo\` (with a Gemini key) to explain any issue.`;
    }

    const markdown = await explainIssue({
      gh,
      gemini,
      repo: entry.repo,
      issue: entry.issue,
      recordedAnswer,
      onStep: (step) => !closed && send('step', step),
    });
    if (!closed) send('done', { markdown: maskSecrets(markdown), ai: Boolean(gemini) || Boolean(recordedAnswer) });
  })()
    .catch((error) => !closed && send('error', { message: maskSecrets(error instanceof Error ? error.message : String(error)) }))
    .finally(() => res.end());
}

const server = http.createServer(async (req, res) => {
  try {
    // Only answer requests addressed to localhost (blocks DNS-rebinding from other sites).
    const host = (req.headers.host ?? '').replace(/:\d+$/, '');
    if (!['localhost', '127.0.0.1'].includes(host)) return json(res, 403, { error: 'Forbidden host' });
    if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed' });

    const url = new URL(req.url ?? '/', 'http://localhost');
    if (url.pathname === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', ...SECURITY_HEADERS });
      return void res.end(readFileSync(PAGE));
    }
    if (url.pathname === '/api/status') {
      return json(res, 200, { demo, ai: demo || Boolean(gemini), githubToken: gh.hasToken, model: config.modelName });
    }
    if (url.pathname === '/api/issues') return await handleIssues(url, res);
    if (url.pathname === '/api/explain') return handleExplain(url, req, res);
    json(res, 404, { error: 'Not found' });
  } catch (error) {
    if (!res.headersSent) json(res, 502, { error: maskSecrets(error instanceof Error ? error.message : String(error)) });
    else res.end();
  }
});

// Bound to loopback only: the GitHub and Gemini keys never leave this machine's server process.
server.listen(port, '127.0.0.1', () => {
  console.log(`merge-mentor UI running at http://localhost:${port}${demo ? '  (demo mode: recorded data)' : ''}`);
  if (!demo && !gemini) console.log('No GEMINI_API_KEY set: the UI will show scores only.');
});
