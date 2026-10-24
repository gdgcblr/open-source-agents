#!/usr/bin/env node
/**
 * Records the data behind `--demo`: the first projects for one language and level, their free issues,
 * Gemini's difficulty ratings (ONE batched call) and ONE mentor explanation. Uses live GitHub and Gemini.
 */
import path from 'node:path';
import { FIXTURE_FILE, loadConfig } from './config.js';
import { GitHubClient, loadFixture, saveFixture } from './github/client.js';
import { fetchIssue, fetchRepo, findRepos } from './github/finder.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { issueKey, rateDifficulties } from './ai/difficulty.js';
import { Gemini } from './ai/gemini.js';
import { maskSecrets } from './ai/mentor.js';
import type { Fixture, Row } from './types.js';
import { DEMO, ISSUE_CANDIDATES_PER_PAGE } from './constants.js';

/** Re-records only the mentor explanation, keeping all recorded GitHub data and ratings (cheapest way to refresh it). */
async function mentorOnly() {
  const config = loadConfig();
  if (!config.geminiApiKey) throw new Error('GEMINI_API_KEY is required to record an explanation.');
  const file = FIXTURE_FILE;
  const fixture = loadFixture(file);
  const target = String(fixture.gemini.mentorFor ?? '');
  const m = target.match(/^(.+)#(\d+)$/);
  if (!m) throw new Error('The recording has no explained issue to refresh.');
  const gh = new GitHubClient(config.githubToken, 'record', fixture);
  const [repo, issue] = await Promise.all([fetchRepo(gh, m[1]), fetchIssue(gh, m[1], Number(m[2]))]);
  console.log(`Re-explaining ${target} …`);
  fixture.gemini.mentor = await explainIssue({ gh, gemini: new Gemini(config.geminiApiKey, config.modelName), repo, issue, onStep: (s) => console.log(`   → ${s}`) });
  saveFixture(file, fixture);
  console.log(`Saved ${path.relative(process.cwd(), file)}`);
}

async function main() {
  if (process.argv.includes('--mentor-only')) return mentorOnly();
  const config = loadConfig();
  const fixture: Fixture = { recordedAt: new Date().toISOString(), github: {}, gemini: {} };
  const now = new Date(fixture.recordedAt).getTime();
  const gh = new GitHubClient(config.githubToken, 'record', fixture);
  gh.onWait = (m) => console.log(`  ${m}`);

  const repos = (await findRepos(gh, DEMO.language, DEMO.level, now)).slice(0, DEMO.projects);
  console.log(`Recording ${repos.length} ${DEMO.language} projects (${DEMO.level}): ${repos.map((r) => r.full_name).join(', ')}`);

  // One project at a time keeps GitHub's secondary rate limit happy.
  const all: Row[] = [];
  for (const [i, repo] of repos.entries()) {
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, DEMO.pauseBetweenProjectsMs)); // GitHub's search API is rate limited per minute
    const { rows, hiddenTaken } = await rankIssues({ gh, repos: [repo], language: DEMO.language, level: DEMO.level, limit: ISSUE_CANDIDATES_PER_PAGE, now });
    console.log(`  ${repo.full_name}: ${rows.length} free issues (${hiddenTaken} hidden)`);
    all.push(...rows);
  }

  fixture.meta = { language: DEMO.language, level: DEMO.level, repos: repos.map((r) => r.full_name) };

  if (config.geminiApiKey && all.length > 0) {
    const gemini = new Gemini(config.geminiApiKey, config.modelName);
    fixture.gemini.difficulty = await rateDifficulties(gemini, all.map((r) => r.issue), DEMO.level);
    console.log(`  rated ${Object.keys(fixture.gemini.difficulty as object).length} issues in one Gemini call`);

    const best = [...all].filter((r) => r.score.status === 'Available').sort((a, b) => b.score.score - a.score.score)[0];
    if (best) {
      console.log(`Explaining ${issueKey(best.issue)} …`);
      const answer = await explainIssue({ gh, gemini, repo: best.repo, issue: best.issue, onStep: (s) => console.log(`   → ${s}`) });
      fixture.gemini.mentor = answer;
      fixture.gemini.mentorFor = issueKey(best.issue);
      fixture.meta.repo = best.repo.full_name;
      // The CLI demo starts from this project, so its repo lookup has to be in the recording too.
      await gh.getJson(`/repos/${best.repo.full_name}`);
    }
  } else {
    console.log('No GEMINI_API_KEY: recording GitHub data only.');
  }

  const file = FIXTURE_FILE;
  saveFixture(file, fixture);
  console.log(`Saved ${path.relative(process.cwd(), file)}`);
}

main().catch((error) => {
  console.error(`Error: ${maskSecrets(error instanceof Error ? error.message : String(error))}`);
  process.exit(1);
});
