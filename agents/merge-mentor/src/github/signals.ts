import { GitHubClient } from './client.js';
import type { ClaimResult, Issue, RepoHealth, Repository, ScoreResult } from '../types.js';
import { CLAIM_PATTERNS, CLAIM_WINDOW_DAYS, CLOSED_PRS_SAMPLE, DAY_MS, MAINTAINER_ROLES, MAX_TIMELINE_PAGES, MERGE_CHANCE, TIMELINE_PAGE_SIZE } from '../constants.js';

export function isClaimComment(body: string): boolean {
  return CLAIM_PATTERNS.some((p) => p.test(body));
}

/** Looks through an issue timeline for an open linked PR or a recent claim comment. */
export function detectClaim(timeline: any[], now: number, repoFullName: string): ClaimResult {
  let claim: ClaimResult = { status: 'Available' };
  for (const event of timeline) {
    const source = event.source?.issue;
    // Only a PR in this same repository counts; mentions from other repos are ignored.
    const sameRepo = source?.repository?.full_name?.toLowerCase() === repoFullName.toLowerCase();
    if (event.event === 'cross-referenced' && sameRepo && source?.pull_request && source.state === 'open') {
      return { status: 'Taken', reason: `PR #${source.number} open` };
    }
    const login: string = event.user?.login ?? event.actor?.login ?? '';
    const isBot = login.endsWith('[bot]') || event.user?.type === 'Bot';
    const recent = now - new Date(event.created_at).getTime() <= CLAIM_WINDOW_DAYS * DAY_MS;
    if (event.event === 'commented' && !isBot && recent && isClaimComment(event.body ?? '')) {
      const days = Math.floor((now - new Date(event.created_at).getTime()) / DAY_MS);
      claim = { status: 'Claimed', reason: `@${login} asked ${days === 0 ? 'today' : `${days}d ago`}` };
    }
  }
  return claim;
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

/** Merge Chance 0-100. The weights and bands live in MERGE_CHANCE (constants.ts). */
export function scoreMergeChance(health: RepoHealth, repoPushedAt: string, issueComments: number, claim: ClaimResult, now: number): number {
  const W = MERGE_CHANCE;
  let score = 0;
  if (health.mergedPRs > 0) score += (health.outsideMerged / health.mergedPRs) * W.outsideContributorPoints;
  if (health.closedPRs > 0) score += (health.mergedPRs / health.closedPRs) * W.mergeRatePoints;

  const median = health.medianDaysToMerge;
  if (median !== null) score += bandPoints(W.mergeSpeedBands, (b) => median <= b.maxDays);

  const daysSincePush = (now - new Date(repoPushedAt).getTime()) / DAY_MS;
  score += bandPoints(W.repoActivityBands, (b) => daysSincePush <= b.maxDays);
  score += bandPoints(W.quietIssueBands, (b) => issueComments <= b.maxComments);

  if (claim.status === 'Taken') score = Math.min(score, W.takenCap);
  if (claim.status === 'Claimed') score -= W.claimedPenalty;
  return Math.max(0, Math.min(100, Math.round(score)));
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
  return { ...claim, health, score: scoreMergeChance(health, repo.pushed_at, issue.comments, claim, now) };
}
