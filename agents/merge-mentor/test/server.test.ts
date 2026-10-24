import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import { RATE_MAX_REQUESTS } from '../src/constants.js';

/** Starts the real web server in demo mode (no network, no keys) and talks to it over HTTP. */
const PORT = 3200 + Math.floor(Math.random() * 600);
let child: ChildProcess;

interface Reply {
  status: number;
  headers: http.IncomingHttpHeaders;
  body: string;
}

function request(path: string, opts: { method?: string; headers?: Record<string, string> } = {}): Promise<Reply> {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: PORT, path, method: opts.method ?? 'GET', headers: opts.headers }, (res) => {
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, headers: res.headers, body }));
    });
    req.on('error', reject);
    req.end();
  });
}

before(async () => {
  child = spawn(process.execPath, ['--import', 'tsx', 'src/server.ts', '--demo', '--port', String(PORT)], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('server did not start')), 20_000);
    child.stdout!.on('data', (d) => {
      if (String(d).includes('running at')) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.on('exit', () => reject(new Error('server exited early')));
  });
});

after(() => void child?.kill());

test('serves the page and status to a normal same-origin browser request', async () => {
  const status = await request('/api/status', { headers: { 'sec-fetch-site': 'same-origin' } });
  assert.equal(status.status, 200);
  assert.equal(JSON.parse(status.body).demo, true);
  assert.equal((await request('/')).status, 200);
});

test('rejects requests addressed to another host (DNS rebinding)', async () => {
  assert.equal((await request('/api/status', { headers: { host: 'evil.example' } })).status, 403);
});

test('rejects cross-site requests and foreign origins (a web page cannot spend your quota)', async () => {
  assert.equal((await request('/api/status', { headers: { 'sec-fetch-site': 'cross-site' } })).status, 403);
  assert.equal((await request('/api/status', { headers: { origin: 'https://evil.example' } })).status, 403);
  assert.equal((await request('/api/status', { headers: { origin: `http://localhost:${PORT}` } })).status, 200);
});

test('only GET is allowed, and unknown paths are 404', async () => {
  assert.equal((await request('/api/projects', { method: 'POST' })).status, 405);
  assert.equal((await request('/api/projects', { method: 'DELETE' })).status, 405);
  assert.equal((await request('/etc/passwd')).status, 404);
});

test('every parameter is validated before anything else happens', async () => {
  assert.equal((await request('/api/issues?repo=../etc&level=beginner')).status, 400);
  assert.equal((await request('/api/issues?repo=a/b/c&level=beginner')).status, 400);
  assert.equal((await request('/api/issues?repo=dexie/Dexie.js&level=god')).status, 400);
  assert.equal((await request('/api/projects?lang=%3Cscript%3E&level=beginner')).status, 400);
  assert.equal((await request('/api/explain?repo=dexie/Dexie.js&number=-1')).status, 400);
});

test('the page gets a strict CSP with a fresh nonce each time, and cannot be framed', async () => {
  const [a, b] = [await request('/'), await request('/')];
  const csp = String(a.headers['content-security-policy']);
  assert.match(csp, /script-src 'nonce-[\w+/=]+'/);
  assert.doesNotMatch(csp.split(';').find((d) => d.includes('script-src')) ?? '', /unsafe-inline/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.match(csp, /default-src 'none'/);
  assert.notEqual(csp, String(b.headers['content-security-policy']), 'nonce must change per response');
  assert.match(a.body, /<script nonce="[\w+/=]+">/);
  assert.equal(a.headers['x-content-type-options'], 'nosniff');
});

test('demo mode walks the recorded flow: projects, one project\'s issues, and the explanation', async () => {
  const projects = JSON.parse((await request('/api/projects?lang=typescript&level=beginner')).body);
  assert.equal(projects.projects.length, 5);

  const issues = JSON.parse((await request('/api/issues?repo=dexie/Dexie.js&level=beginner')).body);
  assert.equal(issues.issues.length, 5);
  assert.equal(issues.issues[0].number, 1032);

  const sse = (await request('/api/explain?repo=dexie/Dexie.js&number=1032')).body;
  assert.match(sse, /^event: done/m);
  assert.match(sse, /Automatic checks/);

  const outside = JSON.parse((await request('/api/issues?repo=bitwarden/clients&level=beginner')).body);
  assert.match(outside.error, /Demo mode only has issues recorded/);
});

test('a runaway client is rate limited', async () => {
  let limited = 0;
  for (let i = 0; i < RATE_MAX_REQUESTS + 10; i++) {
    if ((await request('/api/projects?lang=typescript&level=beginner')).status === 429) limited++;
  }
  assert.ok(limited >= 1, 'expected at least one 429 after the request budget is used');
});
