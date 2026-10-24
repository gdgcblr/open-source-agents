import {detectProjectPath} from './checks/scope.js';
import type {ProjectSource} from './types.js';

const PR_URL = /^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+)\/pull\/(\d+)\/?$/;
const MAX_PAGES = 30;
const MAX_FILE_BYTES = 1_000_000;

interface PullRequest {
  head: {sha: string; repo: {full_name: string} | null};
}

interface PullRequestFile {
  filename: string;
  status: string;
}

export function parsePullRequestUrl(url: string): {owner: string; repo: string; number: number} | null {
  const m = PR_URL.exec(url.trim());
  return m ? {owner: m[1], repo: m[2], number: Number(m[3])} : null;
}

async function githubApi<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'contribution-review-agent',
  };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const res = await fetch(`https://api.github.com${path}`, {headers}).catch((err: Error) => {
    throw new Error(`Could not reach api.github.com (${err.message}). Check your network or proxy.`);
  });
  if (!res.ok) throw new Error(`GitHub API returned ${res.status} for ${path}`);
  return (await res.json()) as T;
}

export async function loadPullRequestSource(url: string): Promise<ProjectSource> {
  const ref = parsePullRequestUrl(url);
  if (!ref) throw new Error(`Not a GitHub pull request URL: ${url}`);
  const base = `/repos/${ref.owner}/${ref.repo}/pulls/${ref.number}`;

  const pr = await githubApi<PullRequest>(base);
  const changed: PullRequestFile[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const batch = await githubApi<PullRequestFile[]>(`${base}/files?per_page=100&page=${page}`);
    changed.push(...batch);
    if (batch.length < 100) break;
  }

  const present = changed.filter((f) => f.status !== 'removed').map((f) => f.filename);
  const projectPath = detectProjectPath(present) ?? '';
  const prefix = `${projectPath}/`;
  const files = projectPath ? present.filter((f) => f.startsWith(prefix)).map((f) => f.slice(prefix.length)) : [];
  const headRepo = pr.head.repo?.full_name ?? `${ref.owner}/${ref.repo}`;

  return {
    label: url,
    projectPath,
    files,
    changedFiles: changed.map((f) => f.filename),
    async readFile(relPath) {
      if (!files.includes(relPath)) return null;
      const encoded = `${prefix}${relPath}`.split('/').map(encodeURIComponent).join('/');
      const res = await fetch(`https://raw.githubusercontent.com/${headRepo}/${pr.head.sha}/${encoded}`);
      if (!res.ok) return null;
      const text = await res.text();
      return text.length > MAX_FILE_BYTES ? null : text;
    },
  };
}
