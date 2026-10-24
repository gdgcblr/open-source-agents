import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import type { Fixture, FixtureMode } from '../types.js';
import { GITHUB_API_HOST, GITHUB_API_VERSION, GITHUB_DEFAULT_RETRY_WAIT_SEC, GITHUB_MAX_RETRY_WAIT_SEC, GITHUB_MIN_RETRY_WAIT_SEC, GITHUB_TIMEOUT_MS, USER_AGENT } from '../constants.js';


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
          ? { issue: { number: e.source.issue.number, state: e.source.issue.state, pull_request: e.source.issue.pull_request ? { merged_at: e.source.issue.pull_request.merged_at ?? null } : undefined, repository: { full_name: e.source.issue.repository?.full_name } } }
          : undefined,
      }));
  }
  if (pathname.endsWith('/pulls') && Array.isArray(data)) {
    return data.map((p) => ({ merged_at: p.merged_at, created_at: p.created_at, author_association: p.author_association, user: p.user ? { login: p.user.login, type: p.user.type } : undefined }));
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
    return { items: data.items.map((r: any) => ({ full_name: r.full_name, stargazers_count: r.stargazers_count, pushed_at: r.pushed_at, default_branch: r.default_branch, language: r.language, description: r.description ? String(r.description).slice(0, 200) : null, html_url: r.html_url })) };
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
    /** Injectable so tests do not really wait out a rate limit. */
    private sleep: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  ) {}

  /** Called when the client pauses for a rate limit, so callers can tell the user. */
  onWait?: (message: string) => void;

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
    const url = new URL(path, `https://${GITHUB_API_HOST}`);
    if (url.protocol !== 'https:' || url.host !== GITHUB_API_HOST) {
      throw new Error(`Blocked request to ${url.host}: only ${GITHUB_API_HOST} is allowed`);
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
      'X-GitHub-Api-Version': GITHUB_API_VERSION,
      'User-Agent': USER_AGENT,
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    let res: Response;
    for (let attempt = 1; ; attempt++) {
      res = await fetch(url, { method: 'GET', headers, signal: AbortSignal.timeout(GITHUB_TIMEOUT_MS) });
      if (res.ok) break;

      const body = (await res.text().catch(() => '')).slice(0, 300);
      const limited = res.status === 403 || res.status === 429;
      const primaryExhausted = limited && res.headers.get('x-ratelimit-remaining') === '0';
      const secondary = limited && !primaryExhausted && (/secondary rate limit/i.test(body) || res.headers.has('retry-after'));
      if (secondary) {
        // GitHub asks clients to slow down briefly after a burst; wait once and retry instead of failing.
        const waitSec = Math.max(GITHUB_MIN_RETRY_WAIT_SEC, Number(res.headers.get('retry-after')) || GITHUB_DEFAULT_RETRY_WAIT_SEC);
        if (attempt === 1 && waitSec <= GITHUB_MAX_RETRY_WAIT_SEC) {
          this.onWait?.(`GitHub asked us to slow down; waiting ${waitSec}s…`);
          await this.sleep(waitSec * 1000);
          continue;
        }
        throw new Error(`GitHub is rate limiting requests. Wait about ${waitSec} seconds and try again.`);
      }
      if (primaryExhausted) {
        throw new Error(`GitHub rate limit reached.${this.token ? '' : ' Add GITHUB_TOKEN to .env to raise it.'}`);
      }
      throw new Error(`GitHub API ${res.status} for ${url.pathname}: ${body.slice(0, 200)}`);
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
