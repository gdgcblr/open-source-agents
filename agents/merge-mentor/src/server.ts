#!/usr/bin/env node
import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { FIXTURE_FILE, PROJECT_ROOT, isValidLevel, loadConfig, normalizeLanguage } from './config.js';
import { GitHubClient, assertDemoSupports, loadFixture } from './github/client.js';
import { fetchIssue, fetchRepo, findRepos } from './github/finder.js';
import { scoreBand } from './github/signals.js';
import { Gemini } from './ai/gemini.js';
import { issueKey } from './ai/difficulty.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { maskSecrets } from './ai/mentor.js';
import type { Fixture, Issue, Level, Repository, Row } from './types.js';
import { ALLOWED_HOSTS, API_CSP, BASE_HEADERS, DEFAULT_PORT, ISSUE_CANDIDATES_PER_PAGE, LEVELS, MAX_CACHE_ENTRIES, MAX_PAGES, MAX_PARALLEL_EXPLAINS, RATE_MAX_REQUESTS, RATE_WINDOW_MS, REPO_PAGE_SIZE, REPO_REF, SERVER_HOST } from './constants.js';

const { values } = parseArgs({
  options: { demo: { type: 'boolean', default: false }, port: { type: 'string' } },
});

const config = loadConfig();
const demo = values.demo!;
const fixture: Fixture | undefined = demo ? loadFixture(FIXTURE_FILE) : undefined;
const now = fixture ? new Date(fixture.recordedAt).getTime() : undefined;
const gh = new GitHubClient(config.githubToken, demo ? 'replay' : 'live', fixture);
const gemini = !demo && config.geminiApiKey ? new Gemini(config.geminiApiKey, config.modelName) : undefined;
const port = Number(values.port ?? process.env.PORT ?? DEFAULT_PORT);

/** Rows from the most recent searches, so opening an issue does not refetch it. */
const known = new Map<string, { issue: Issue; repo: Repository }>();
/** Projects seen in the project list, so opening one does not refetch it. */
const knownRepos = new Map<string, Repository>();

const pageHtml = readFileSync(path.join(PROJECT_ROOT, 'web', 'index.html'), 'utf8');
/** JSON and event-stream responses never need to load anything. */
const API_HEADERS = { ...BASE_HEADERS, 'Content-Security-Policy': API_CSP };
/** The page may run only its own inline script (matched by a fresh nonce) and talk only to this server. */
const pageHeaders = (nonce: string) => ({
  ...BASE_HEADERS,
  'Content-Security-Policy': `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
});

/** Insert into a size-limited Map, dropping the oldest entry when it grows too large. */
function remember<K, V>(map: Map<K, V>, key: K, value: V): void {
  map.delete(key);
  map.set(key, value);
  if (map.size > MAX_CACHE_ENTRIES) map.delete(map.keys().next().value as K);
}

/** Simple per-process limit so a runaway page or script cannot hammer GitHub and Gemini through this server. */
let windowStart = Date.now();
let windowCount = 0;
function rateLimited(): boolean {
  if (Date.now() - windowStart > RATE_WINDOW_MS) {
    windowStart = Date.now();
    windowCount = 0;
  }
  return ++windowCount > RATE_MAX_REQUESTS;
}

let activeExplains = 0;

function json(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...API_HEADERS });
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

const REPO_RE = REPO_REF;

function parseLevel(url: URL): Level | null {
  const level = url.searchParams.get('level') ?? 'beginner';
  return isValidLevel(level) ? level : null;
}

function parsePage(url: URL, max: number): number {
  return Math.max(1, Math.min(max, Math.floor(Number(url.searchParams.get('page'))) || 1));
}

/** Step 1: only the project list (one GitHub search, no scoring, no Gemini). */
async function handleProjects(url: URL, res: http.ServerResponse): Promise<void> {
  const lang = (url.searchParams.get('lang') ?? '').trim();
  const level = parseLevel(url);
  if (!/^[\w.+#-]{1,30}$/.test(lang)) return json(res, 400, { error: 'Enter a language such as typescript, python or go.' });
  if (!level) return json(res, 400, { error: `Level must be one of: ${LEVELS.join(', ')}` });

  const language = normalizeLanguage(lang);
  assertDemoSupports(fixture, language, level);
  const page = parsePage(url, MAX_PAGES);
  if (fixture && page > 1) return json(res, 200, { projects: [], page, hasMore: false });

  let repos = await findRepos(gh, language, level, now ?? Date.now(), page);
  // The demo recording has issues for its first projects only; do not offer the others.
  const demoRepos = fixture?.meta?.repos;
  if (demoRepos) repos = repos.filter((r) => demoRepos.some((d) => d.toLowerCase() === r.full_name.toLowerCase()));
  for (const r of repos) remember(knownRepos, r.full_name.toLowerCase(), r);
  json(res, 200, {
    projects: repos.map((r) => ({
      full_name: r.full_name,
      stars: r.stargazers_count,
      language: r.language,
      description: r.description ?? null,
      pushed: r.pushed_at,
      url: r.html_url ?? `https://github.com/${r.full_name}`,
    })),
    page,
    hasMore: repos.length >= REPO_PAGE_SIZE,
  });
}

/** Step 2: free issues of one chosen project (claim check, Merge Chance, difficulty rating). */
async function handleIssues(url: URL, res: http.ServerResponse): Promise<void> {
  const repoName = url.searchParams.get('repo') ?? '';
  const level = parseLevel(url);
  if (!REPO_RE.test(repoName)) return json(res, 400, { error: 'Choose a project first.' });
  if (!level) return json(res, 400, { error: `Level must be one of: ${LEVELS.join(', ')}` });

  if (fixture) {
    const m = fixture.meta;
    const covered = m?.repos ?? (m?.repo ? [m.repo] : []);
    if (!covered.some((c) => c.toLowerCase() === repoName.toLowerCase()) || m?.level !== level) {
      throw new Error(`Demo mode only has issues recorded for the first ${covered.length} ${m?.language ?? 'typescript'} projects (${m?.level ?? 'beginner'} level). Run without --demo (npm run ui) to browse any project live.`);
    }
  }
  const page = parsePage(url, MAX_PAGES);
  if (fixture && page > 1) return json(res, 200, { issues: [], hiddenTaken: 0, page, hasMore: false });

  const repo = knownRepos.get(repoName.toLowerCase()) ?? (await fetchRepo(gh, repoName));
  remember(knownRepos, repoName.toLowerCase(), repo);

  const { rows, hiddenTaken, hasMore } = await rankIssues({
    gh,
    gemini,
    repos: [repo],
    language: repo.language ?? '',
    level,
    limit: ISSUE_CANDIDATES_PER_PAGE,
    page,
    now: now ?? Date.now(),
    recordedRatings: fixture ? ((fixture.gemini.difficulty ?? {}) as Record<string, any>) : undefined,
  });
  for (const r of rows) remember(known, issueKey(r.issue), { issue: r.issue, repo: r.repo });
  json(res, 200, { issues: rows.map(toJson), hiddenTaken, page, hasMore });
}

function handleExplain(url: URL, req: http.IncomingMessage, res: http.ServerResponse): void {
  const repoName = url.searchParams.get('repo') ?? '';
  const number = Number(url.searchParams.get('number'));
  if (!REPO_RE.test(repoName) || !Number.isInteger(number) || number < 1) {
    return json(res, 400, { error: 'Invalid issue reference.' });
  }

  if (activeExplains >= MAX_PARALLEL_EXPLAINS) return json(res, 429, { error: 'Two explanations are already running. Wait for one to finish.' });
  activeExplains++;

  res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', Connection: 'keep-alive', ...API_HEADERS });
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
      isCancelled: () => closed,
    });
    if (!closed) send('done', { markdown: maskSecrets(markdown), ai: Boolean(gemini) || Boolean(recordedAnswer) });
  })()
    .catch((error) => !closed && send('error', { message: maskSecrets(error instanceof Error ? error.message : String(error)) }))
    .finally(() => {
      activeExplains--;
      res.end();
    });
}

const server = http.createServer(async (req, res) => {
  try {
    // Only answer requests addressed to localhost (blocks DNS-rebinding from other sites).
    const host = (req.headers.host ?? '').replace(/:\d+$/, '');
    if (!ALLOWED_HOSTS.includes(host)) return json(res, 403, { error: 'Forbidden host' });
    if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed' });

    // Block other websites from driving this server through the visitor's browser (it would spend their quota).
    const site = req.headers['sec-fetch-site'];
    if (site && site !== 'same-origin' && site !== 'none') return json(res, 403, { error: 'Cross-site requests are not allowed' });
    const origin = req.headers.origin;
    if (origin) {
      let allowed = false;
      try {
        const o = new URL(origin);
        allowed = ALLOWED_HOSTS.some((h) => o.host === `${h}:${port}`);
      } catch { /* malformed Origin header: not allowed */ }
      if (!allowed) return json(res, 403, { error: 'Cross-origin requests are not allowed' });
    }

    const url = new URL(req.url ?? '/', 'http://localhost');
    if (url.pathname.startsWith('/api/') && url.pathname !== '/api/status' && rateLimited()) {
      return json(res, 429, { error: 'Too many requests. Slow down for a minute.' });
    }
    if (url.pathname === '/') {
      const nonce = randomBytes(16).toString('base64');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...pageHeaders(nonce) });
      return void res.end(pageHtml.replace('<script>', `<script nonce="${nonce}">`));
    }
    if (url.pathname === '/api/status') {
      return json(res, 200, { demo, ai: demo || Boolean(gemini), githubToken: gh.hasToken, model: config.modelName });
    }
    if (url.pathname === '/api/projects') return await handleProjects(url, res);
    if (url.pathname === '/api/issues') return await handleIssues(url, res);
    if (url.pathname === '/api/explain') return handleExplain(url, req, res);
    json(res, 404, { error: 'Not found' });
  } catch (error) {
    if (!res.headersSent) json(res, 502, { error: maskSecrets(error instanceof Error ? error.message : String(error)) });
    else res.end();
  }
});

// Bound to loopback only: the GitHub and Gemini keys never leave this machine's server process.
server.listen(port, SERVER_HOST, () => {
  console.log(`merge-mentor UI running at http://localhost:${port}${demo ? '  (demo mode: recorded data)' : ''}`);
  if (!demo && !gemini) console.log('No GEMINI_API_KEY set: the UI will show scores only.');
});
