import { existsSync, readFileSync, writeFileSync } from 'node:fs';

const API_HOST = 'api.github.com';
const TIMEOUT_MS = 15_000;

/** Recorded responses used by --demo (replay) and --record. */
export interface Fixture {
  recordedAt: string;
  /** The one search the recording covers; demo mode refuses anything else. */
  meta?: { language: string; level: string };
  github: Record<string, unknown>;
  gemini: Record<string, unknown>;
}

export type FixtureMode = 'live' | 'record' | 'replay';

export function loadFixture(file: string): Fixture {
  if (!existsSync(file)) throw new Error(`Demo data not found at ${file}. Run "npm run record-demo" first.`);
  return JSON.parse(readFileSync(file, 'utf8')) as Fixture;
}

/** Keeps only the fields merge-mentor reads, so the committed demo data stays small. */
export function slimForFixture(key: string, data: any): unknown {
  const pathname = key.replace(/^RAW /, '').split('?')[0];
  if (pathname.endsWith('/timeline') && Array.isArray(data)) {
    return data
      .filter((e) => e.event === 'cross-referenced' || e.event === 'commented')
      .map((e) => ({
        event: e.event,
        created_at: e.created_at,
        body: typeof e.body === 'string' ? e.body.slice(0, 300) : undefined,
        user: e.user ? { login: e.user.login, type: e.user.type } : undefined,
        source: e.source?.issue
          ? { issue: { number: e.source.issue.number, state: e.source.issue.state, pull_request: e.source.issue.pull_request ? {} : undefined, repository: { full_name: e.source.issue.repository?.full_name } } }
          : undefined,
      }));
  }
  if (pathname.endsWith('/pulls') && Array.isArray(data)) {
    return data.map((p) => ({ merged_at: p.merged_at, created_at: p.created_at, author_association: p.author_association }));
  }
  if (pathname.includes('/git/trees/') && data?.tree) {
    return { tree: data.tree.filter((n: any) => n.type === 'blob').map((n: any) => ({ path: n.path, type: n.type })) };
  }
  if (pathname.endsWith('/comments') && Array.isArray(data)) {
    return data.map((c) => ({ body: String(c.body ?? '').slice(0, 800), user: { login: c.user?.login } }));
  }
  if (pathname === '/search/issues' && data?.items) {
    return { items: data.items.map((i: any) => ({ number: i.number, title: i.title, html_url: i.html_url, repository_url: i.repository_url, body: String(i.body ?? '').slice(0, 1500), comments: i.comments, created_at: i.created_at, updated_at: i.updated_at, labels: (i.labels ?? []).map((l: any) => ({ name: l.name })) })) };
  }
  if (pathname === '/search/repositories' && data?.items) {
    return { items: data.items.map((r: any) => ({ full_name: r.full_name, stargazers_count: r.stargazers_count, pushed_at: r.pushed_at, default_branch: r.default_branch, language: r.language })) };
  }
  return data;
}

export function saveFixture(file: string, fixture: Fixture): void {
  writeFileSync(file, JSON.stringify(fixture));
}

/**
 * Read-only GitHub REST client.
 * Guardrails: it can only send GET requests, only to api.github.com, with a timeout,
 * and error messages never include the token.
 */
export class GitHubClient {
  constructor(
    private token: string | undefined,
    private mode: FixtureMode = 'live',
    private fixture?: Fixture,
  ) {}

  get hasToken(): boolean {
    return Boolean(this.token) || this.mode === 'replay';
  }

  getJson<T = any>(path: string, params: Record<string, string | number> = {}): Promise<T> {
    return this.get(path, params, false) as Promise<T>;
  }

  /** Fetch a file's raw text through the contents API. */
  getRaw(path: string, params: Record<string, string | number> = {}): Promise<string> {
    return this.get(path, params, true) as Promise<string>;
  }

  private async get(path: string, params: Record<string, string | number>, raw: boolean): Promise<unknown> {
    const url = new URL(path, `https://${API_HOST}`);
    if (url.protocol !== 'https:' || url.host !== API_HOST) {
      throw new Error(`Blocked request to ${url.host}: only ${API_HOST} is allowed`);
    }
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
    const cacheKey = `${raw ? 'RAW ' : ''}${url.pathname}${url.search}`;

    if (this.mode === 'replay') {
      // The demo replays a single recorded search, so the two search endpoints match by path only.
      const exact = this.fixture && cacheKey in this.fixture.github;
      const byPath = !exact && url.pathname.startsWith('/search/') && this.fixture
        ? Object.keys(this.fixture.github).find((k) => k.split('?')[0] === url.pathname)
        : undefined;
      if (byPath) return this.fixture!.github[byPath];
      if (!this.fixture || !exact) {
        throw new Error('Demo mode only has recorded data for typescript at beginner level. Run without --demo (npm run ui) to search any language live.');
      }
      return this.fixture.github[cacheKey];
    }

    const headers: Record<string, string> = {
      Accept: raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'merge-mentor',
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const res = await fetch(url, { method: 'GET', headers, signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!res.ok) {
      if ((res.status === 403 || res.status === 429) && res.headers.get('x-ratelimit-remaining') === '0') {
        throw new Error(`GitHub rate limit reached.${this.token ? '' : ' Add GITHUB_TOKEN to .env to raise it.'}`);
      }
      const body = (await res.text().catch(() => '')).slice(0, 200);
      throw new Error(`GitHub API ${res.status} for ${url.pathname}: ${body}`);
    }
    const data = raw ? await res.text() : await res.json();

    if (this.mode === 'record' && this.fixture) this.fixture.github[cacheKey] = slimForFixture(cacheKey, data);
    return data;
  }
}

/** Demo mode only replays the recorded language and level; fail with a clear message for anything else. */
export function assertDemoSupports(fixture: Fixture | undefined, language: string, level: string): void {
  const meta = fixture?.meta ?? { language: 'typescript', level: 'beginner' };
  if (fixture && (language !== meta.language || level !== meta.level)) {
    throw new Error(`Demo mode only has recorded data for ${meta.language} at ${meta.level} level. Run without --demo (npm run ui) to search any language live.`);
  }
}
