import { Level } from './config.js';
import { GitHubClient } from './github.js';
import { Gemini } from './gemini.js';
import { Issue, Repository, findIssues, findRepos } from './finder.js';
import { RepoHealth, getMergeChance } from './signals.js';
import { DifficultyResult, adjustScoreForDifficulty, issueKey, rateDifficulties } from './difficulty.js';
import { basicGuide, mentorIssue } from './mentor.js';
import type { Row } from './render.js';

export interface RankOptions {
  gh: GitHubClient;
  gemini?: Gemini;
  language: string;
  level: Level;
  /** Max candidate issues to check on this page. */
  limit: number;
  page?: number;
  /** Drop issues that already have an open PR (default true). */
  hideTaken?: boolean;
  now: number;
  /** Ratings recorded for --demo; used instead of calling Gemini. */
  recordedRatings?: Record<string, DifficultyResult>;
  log?: (message: string) => void;
}

export interface RankResult {
  rows: Row[];
  ratings: Record<string, DifficultyResult>;
  /** Candidates dropped because an open PR already covers them. */
  hiddenTaken: number;
  hasMore: boolean;
}

/** Runs `fn` over `items` with at most `size` in flight, so GitHub's secondary rate limit is never triggered. */
async function mapPool<T, R>(items: T[], size: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(size, items.length) }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]);
      }
    }),
  );
  return out;
}

/** Steps 1-4: find repos and issues, check claims, compute Merge Chance, rate difficulty, rank. */
export async function rankIssues(o: RankOptions): Promise<RankResult> {
  const repos = await findRepos(o.gh, o.language, o.level, o.now);
  const { issues, hasMore } = await findIssues(o.gh, repos, o.level, o.limit, o.page ?? 1);
  if (issues.length === 0) return { rows: [], ratings: {}, hiddenTaken: 0, hasMore };
  o.log?.(`${repos.length} repos, ${issues.length} open issues. Checking claims and merge history…`);

  const repoByName = new Map(repos.map((r) => [r.full_name, r]));
  const healthCache = new Map<string, Promise<RepoHealth>>();
  const scored = await mapPool(issues, 4, async (issue) => {
    const repo = repoByName.get(issue.repo_full_name)!;
    return { issue, repo, score: await getMergeChance(o.gh, issue, repo, healthCache, o.now) };
  });

  // An issue with an open PR is not worth the reader's time, and rating it would waste Gemini quota.
  const kept = o.hideTaken === false ? scored : scored.filter((s) => s.score.status !== 'Taken');
  const hiddenTaken = scored.length - kept.length;

  let ratings: Record<string, DifficultyResult> = o.recordedRatings ?? {};
  if (!o.recordedRatings && o.gemini && kept.length > 0) {
    try {
      ratings = await rateDifficulties(o.gemini, kept.map((k) => k.issue), o.level);
    } catch (error) {
      o.log?.(`Difficulty rating skipped: ${(error as Error).message.slice(0, 120)}`);
    }
  }

  const rank = (r: Row) => adjustScoreForDifficulty(r.score.score, r.difficulty?.difficulty, o.level);
  const rows: Row[] = kept.map((s) => ({ ...s, difficulty: ratings[issueKey(s.issue)] })).sort((a, b) => rank(b) - rank(a));
  return { rows, ratings, hiddenTaken, hasMore };
}

export interface ExplainOptions {
  gh: GitHubClient;
  gemini?: Gemini;
  repo: Repository;
  issue: Issue;
  /** Recorded answer used by --demo instead of calling Gemini. */
  recordedAnswer?: string;
  onStep?: (line: string) => void;
}

/** Step 5: the mentor agent (or a plain pointer when there is no Gemini key). */
export async function explainIssue(o: ExplainOptions): Promise<string> {
  if (o.recordedAnswer !== undefined) return o.recordedAnswer;
  const ctx = { gh: o.gh, repo: o.repo.full_name, branch: o.repo.default_branch };
  if (!o.gemini) return basicGuide(ctx, o.issue);

  const raw = await o.gh.getJson<any[]>(`/repos/${o.repo.full_name}/issues/${o.issue.number}/comments`, { per_page: 20 });
  const comments = raw.map((c) => ({ user: c.user?.login ?? 'unknown', body: String(c.body ?? '') }));
  return mentorIssue({ gemini: o.gemini, ctx, issue: o.issue, comments, onStep: o.onStep });
}
