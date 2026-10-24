import { GitHubClient } from './client.js';
import type { ClaimResult, Issue, RepoHealth, Repository, ScorePart, ScoreResult } from '../types.js';
import { CLAIM_PATTERNS, CLAIM_WINDOW_DAYS, CLOSED_PRS_SAMPLE, DAY_MS, MAINTAINER_ROLES, MAX_TIMELINE_PAGES, MERGE_CHANCE, TIMELINE_PAGE_SIZE } from '../constants.js';

export function isClaimComment(body: string): boolean {
  return CLAIM_PATTERNS.some((p) => p.test(body));
}

/**
 * Looks through an issue timeline. Priority: an open linked PR (Taken), then a merged PR that references
 * the issue although it is still open (probably already Fixed), then a recent claim comment (Claimed).
 */
export function detectClaim(timeline: any[], now: number, repoFullName: string): ClaimResult {
  let claim: ClaimResult = { status: 'Available' };
  let fixed: ClaimResult | undefined;
  for (const event of timeline) {
    const source = event.source?.issue;
    // Only a PR in this same repository counts; mentions from other repos are ignored.
    const sameRepo = source?.repository?.full_name?.toLowerCase() === repoFullName.toLowerCase();
    if (event.event === 'cross-referenced' && sameRepo && source?.pull_request && source.state === 'open') {
      return { status: 'Taken', reason: `PR #${source.number} open` };
    }
    if (event.event === 'cross-referenced' && sameRepo && source?.pull_request?.merged_at) {
      fixed = { status: 'Fixed', reason: `PR #${source.number} already merged` };
    }
    const login: string = event.user?.login ?? event.actor?.login ?? '';
    const isBot = login.endsWith('[bot]') || event.user?.type === 'Bot';
    const recent = now - new Date(event.created_at).getTime() <= CLAIM_WINDOW_DAYS * DAY_MS;
    if (event.event === 'commented' && !isBot && recent && isClaimComment(event.body ?? '')) {
      const days = Math.floor((now - new Date(event.created_at).getTime()) / DAY_MS);
      claim = { status: 'Claimed', reason: `@${login} asked ${days === 0 ? 'today' : `${days}d ago`}` };
    }
  }
  return fixed ?? claim;
}

const isBot = (pr: any) => pr.user?.type === 'Bot' || String(pr.user?.login ?? '').endsWith('[bot]');

export function computeRepoHealth(allClosedPulls: any[]): RepoHealth {
  // Dependabot/Renovate merges say nothing about how welcoming a repo is to people, so they are ignored.
  const closedPulls = allClosedPulls.filter((pr) => !isBot(pr));
  const merged = closedPulls.filter((pr) => pr.merged_at);
  const days = merged
    .map((pr) => (new Date(pr.merged_at).getTime() - new Date(pr.created_at).getTime()) / DAY_MS)
    .sort((a, b) => a - b);
  return {
    closedPRs: closedPulls.length,
    mergedPRs: merged.length,
    outsideMerged: merged.filter((pr) => !MAINTAINER_ROLES.includes(pr.author_association)).length,
    medianDaysToMerge: days.length ? days[Math.floor(days.length / 2)] : null,
  };
}

/** Points from the first band the value fits in (bands run from best to worst). */
function bandPoints<T extends { points: number }>(bands: readonly T[], fits: (band: T) => boolean): number {
  return bands.find(fits)?.points ?? 0;
}

const round1 = (n: number) => Math.round(n * 10) / 10;
const maxPoints = (bands: readonly { points: number }[]) => Math.max(...bands.map((b) => b.points));

/**
 * Merge Chance 0-100, built line by line so it can be explained to the user.
 * The weights and bands live in MERGE_CHANCE (constants.ts).
 */
export function explainMergeChance(
  health: RepoHealth,
  repoPushedAt: string,
  issueComments: number,
  claim: ClaimResult,
  now: number,
): { total: number; parts: ScorePart[] } {
  const W = MERGE_CHANCE;
  const parts: ScorePart[] = [];

  const outside = health.mergedPRs > 0 ? (health.outsideMerged / health.mergedPRs) * W.outsideContributorPoints : 0;
  parts.push({
    label: 'Outside contributors get merged',
    points: outside,
    max: W.outsideContributorPoints,
    note: health.mergedPRs > 0 ? `${health.outsideMerged} of ${health.mergedPRs} recent merged PRs came from outside the team` : 'no recent merged PRs to learn from',
  });

  const rate = health.closedPRs > 0 ? (health.mergedPRs / health.closedPRs) * W.mergeRatePoints : 0;
  parts.push({
    label: 'Most PRs get merged',
    points: rate,
    max: W.mergeRatePoints,
    note: health.closedPRs > 0 ? `${health.mergedPRs} of ${health.closedPRs} recently closed PRs were merged` : 'no recently closed PRs',
  });

  const median = health.medianDaysToMerge;
  parts.push({
    label: 'PRs merge quickly',
    points: median !== null ? bandPoints(W.mergeSpeedBands, (b) => median <= b.maxDays) : 0,
    max: maxPoints(W.mergeSpeedBands),
    note: median !== null ? `median ${round1(median)} days from opening to merge` : 'no merge times to measure',
  });

  const daysSincePush = (now - new Date(repoPushedAt).getTime()) / DAY_MS;
  parts.push({
    label: 'The project is active',
    points: bandPoints(W.repoActivityBands, (b) => daysSincePush <= b.maxDays),
    max: maxPoints(W.repoActivityBands),
    note: `last push ${Math.max(0, Math.round(daysSincePush))} days ago`,
  });

  parts.push({
    label: 'The issue is quiet',
    points: bandPoints(W.quietIssueBands, (b) => issueComments <= b.maxComments),
    max: maxPoints(W.quietIssueBands),
    note: `${issueComments} comment${issueComments === 1 ? '' : 's'} so far`,
  });

  let total = parts.reduce((sum, p) => sum + p.points, 0);
  if ((claim.status === 'Taken' || claim.status === 'Fixed') && total > W.takenCap) {
    parts.push({ label: 'Capped: open PR or already fixed', points: W.takenCap - total, max: 0, note: `${claim.reason ?? ''}`.trim() || 'someone else has this covered' });
    total = W.takenCap;
  }
  if (claim.status === 'Claimed') {
    parts.push({ label: 'Recently claimed', points: -W.claimedPenalty, max: 0, note: claim.reason ?? 'someone asked to work on it' });
    total -= W.claimedPenalty;
  }
  return { total: Math.max(0, Math.min(100, Math.round(total))), parts: parts.map((p) => ({ ...p, points: round1(p.points) })) };
}

/** Merge Chance 0-100 (just the number). */
export function scoreMergeChance(health: RepoHealth, repoPushedAt: string, issueComments: number, claim: ClaimResult, now: number): number {
  return explainMergeChance(health, repoPushedAt, issueComments, claim, now).total;
}

export function scoreBand(score: number): 'High' | 'Medium' | 'Low' {
  return score >= MERGE_CHANCE.bandHigh ? 'High' : score >= MERGE_CHANCE.bandMedium ? 'Medium' : 'Low';
}

/** Reads the whole timeline (up to 500 events) so a claim or PR deep in a long thread is not missed. */
async function fetchTimeline(gh: GitHubClient, repoFullName: string, issueNumber: number): Promise<any[]> {
  const path = `/repos/${repoFullName}/issues/${issueNumber}/timeline`;
  let events: any[] = await gh.getJson<any[]>(path, { per_page: TIMELINE_PAGE_SIZE });
  for (let page = 2; events.length === TIMELINE_PAGE_SIZE * (page - 1) && page <= MAX_TIMELINE_PAGES; page++) {
    events = events.concat(await gh.getJson<any[]>(path, { per_page: TIMELINE_PAGE_SIZE, page }));
  }
  return events;
}

/** Claim check + Merge Chance for one issue. Repo health is cached per repo. */
export async function getMergeChance(
  gh: GitHubClient,
  issue: Issue,
  repo: Repository,
  healthCache: Map<string, Promise<RepoHealth>>,
  now: number,
): Promise<ScoreResult> {
  if (!healthCache.has(repo.full_name)) {
    healthCache.set(
      repo.full_name,
      gh
        .getJson(`/repos/${repo.full_name}/pulls`, { state: 'closed', sort: 'updated', direction: 'desc', per_page: CLOSED_PRS_SAMPLE })
        .then(computeRepoHealth),
    );
  }
  const [timeline, health] = await Promise.all([
    fetchTimeline(gh, repo.full_name, issue.number),
    healthCache.get(repo.full_name)!,
  ]);
  const claim = detectClaim(timeline, now, repo.full_name);
  const { total, parts } = explainMergeChance(health, repo.pushed_at, issue.comments, claim, now);
  return { ...claim, health, score: total, parts };
}
