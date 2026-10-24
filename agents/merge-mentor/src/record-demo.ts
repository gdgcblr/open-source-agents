#!/usr/bin/env node
/**
 * Records the data behind `--demo`: the first projects for one language and level, their free issues,
 * Gemini's difficulty ratings (ONE batched call) and ONE mentor explanation. Uses live GitHub and Gemini.
 */
import path from 'node:path';
import { PROJECT_ROOT, loadConfig } from './config.js';
import { Fixture, GitHubClient, loadFixture, saveFixture } from './github.js';
import { fetchIssue, fetchRepo, findRepos } from './finder.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { issueKey, rateDifficulties } from './difficulty.js';
import { Gemini } from './gemini.js';
import { maskSecrets } from './mentor.js';
import type { Row } from './render.js';

const LANGUAGE = 'typescript';
const LEVEL = 'beginner';
const PROJECTS = 5;

/** Re-records only the mentor explanation, keeping all recorded GitHub data and ratings (cheapest way to refresh it). */
async function mentorOnly() {
  const config = loadConfig();
  if (!config.geminiApiKey) throw new Error('GEMINI_API_KEY is required to record an explanation.');
  const file = path.join(PROJECT_ROOT, 'fixtures', 'demo.json');
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

  const repos = (await findRepos(gh, LANGUAGE, LEVEL, now)).slice(0, PROJECTS);
  console.log(`Recording ${repos.length} ${LANGUAGE} projects (${LEVEL}): ${repos.map((r) => r.full_name).join(', ')}`);

  // One project at a time keeps GitHub's secondary rate limit happy.
  const all: Row[] = [];
  for (const [i, repo] of repos.entries()) {
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, 8_000)); // GitHub's search API is rate limited per minute
    const { rows, hiddenTaken } = await rankIssues({ gh, repos: [repo], language: LANGUAGE, level: LEVEL, limit: 20, now });
    console.log(`  ${repo.full_name}: ${rows.length} free issues (${hiddenTaken} hidden)`);
    all.push(...rows);
  }

  fixture.meta = { language: LANGUAGE, level: LEVEL, repos: repos.map((r) => r.full_name) };

  if (config.geminiApiKey && all.length > 0) {
    const gemini = new Gemini(config.geminiApiKey, config.modelName);
    fixture.gemini.difficulty = await rateDifficulties(gemini, all.map((r) => r.issue), LEVEL);
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

  const file = path.join(PROJECT_ROOT, 'fixtures', 'demo.json');
  saveFixture(file, fixture);
  console.log(`Saved ${path.relative(process.cwd(), file)}`);
}

main().catch((error) => {
  console.error(`Error: ${maskSecrets(error instanceof Error ? error.message : String(error))}`);
  process.exit(1);
});
