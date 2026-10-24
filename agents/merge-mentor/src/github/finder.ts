import { GitHubClient } from './client.js';
import type { Issue, Level, Repository } from '../types.js';
import { ACTIVE_WITHIN_DAYS, DAY_MS, ISSUES_PER_PROJECT_MIXED, ISSUES_PER_PROJECT_OPEN, ISSUE_PAGE_SIZE, LEVEL_PROFILES, MAX_STARS, MIN_STARS, REPO_PAGE_SIZE, REPO_REF } from '../constants.js';

/** Active, well-starred repos whose main language matches and that have issues for this level. */
export async function findRepos(gh: GitHubClient, language: string, level: Level, now: number, page = 1): Promise<Repository[]> {
  const since = new Date(now - ACTIVE_WITHIN_DAYS * DAY_MS).toISOString().slice(0, 10);
  const q = [
    `language:${language}`,
    // Mid-size repos: giants like excalidraw are the most contested, small ones merge outside PRs sooner.
    `stars:${MIN_STARS}..${MAX_STARS}`,
    'archived:false',
    `pushed:>${since}`,
    LEVEL_PROFILES[level].repoQualifier,
  ].join(' ');
  const result = await gh.getJson('/search/repositories', { q, sort: 'stars', order: 'desc', per_page: REPO_PAGE_SIZE, page });
  return result.items ?? [];
}

/**
 * Open, unassigned issues with level labels and no linked pull request, quietest first.
 * Sorted by fewest comments (not "recently updated": recent activity usually means someone is already on it).
 * `limit` caps how many candidates are returned.
 */
export async function findIssues(
  gh: GitHubClient,
  repos: Repository[],
  level: Level,
  limit: number,
  page = 1,
): Promise<{ issues: Issue[]; hasMore: boolean }> {
  if (repos.length === 0) return { issues: [], hasMore: false };

  // A single label: qualifier with comma-separated values means "any of these labels".
  const labels = LEVEL_PROFILES[level].labels.map((l) => `"${l}"`).join(',');
  const q = ['is:issue', 'is:open', 'no:assignee', '-linked:pr', `label:${labels}`, ...repos.map((r) => `repo:${r.full_name}`)].join(' ');
  const result = await gh.getJson('/search/issues', { q, sort: 'comments', order: 'asc', per_page: ISSUE_PAGE_SIZE, page });
  const items: any[] = result.items ?? [];

  // Browsing one project shows its issues (up to 20); across many projects, 3 each keeps the list varied.
  const cap = repos.length === 1 ? ISSUES_PER_PROJECT_OPEN : ISSUES_PER_PROJECT_MIXED;
  const allowed = new Set(repos.map((r) => r.full_name.toLowerCase()));
  const perRepo = new Map<string, number>();
  const issues: Issue[] = [];
  for (const item of items) {
    if (item.pull_request) continue;
    const repoName = item.repository_url.split('/').slice(-2).join('/');
    if (!allowed.has(repoName.toLowerCase())) continue;
    const count = perRepo.get(repoName) ?? 0;
    if (count >= cap) continue;
    perRepo.set(repoName, count + 1);
    issues.push({ ...item, repo_full_name: repoName });
    if (issues.length >= limit) break;
  }
  return { issues, hasMore: items.length >= ISSUE_PAGE_SIZE };
}

/** Parse "owner/repo#123" or a GitHub issue URL. */
export function parseIssueRef(ref: string): { repo: string; number: number } | null {
  const match =
    ref.match(/^([\w.-]+\/[\w.-]+)#(\d+)$/) ??
    ref.match(/github\.com\/([\w.-]+\/[\w.-]+)\/issues\/(\d+)/);
  return match && REPO_REF.test(match[1]) ? { repo: match[1], number: Number(match[2]) } : null;
}

export async function fetchRepo(gh: GitHubClient, fullName: string): Promise<Repository> {
  return gh.getJson(`/repos/${fullName}`);
}

export async function fetchIssue(gh: GitHubClient, fullName: string, number: number): Promise<Issue> {
  const item = await gh.getJson(`/repos/${fullName}/issues/${number}`);
  if (item.pull_request) throw new Error(`${fullName}#${number} is a pull request, not an issue`);
  return { ...item, repo_full_name: fullName };
}
