#!/usr/bin/env node
import { parseArgs } from 'node:util';
import path from 'node:path';
import readline from 'node:readline/promises';
import pc from 'picocolors';
import { FIXTURE_FILE, isValidLevel, loadConfig, normalizeLanguage } from './config.js';
import { GitHubClient, assertDemoSupports, loadFixture, saveFixture } from './github/client.js';
import { fetchIssue, fetchRepo, findRepos, parseIssueRef } from './github/finder.js';
import { issueKey } from './ai/difficulty.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { Gemini } from './ai/gemini.js';
import { maskSecrets } from './ai/mentor.js';
import { renderMentor, renderTable, saveMarkdown } from './render.js';
import type { DifficultyResult, Fixture, FixtureMode, Issue, Level, Repository } from './types.js';
import { CLI_DEFAULT_LIMIT, CLI_MAX_LIMIT, LEVELS, REPO_REF } from './constants.js';


const HELP = `merge-mentor: from "I know TypeScript" to your first merged PR

Usage:
  merge-mentor --lang <language> [--level beginner|intermediate|advanced]
  merge-mentor --issue owner/repo#123

Options:
  --lang <name>      Language you are good at (e.g. typescript, python, go)
  --level <level>    beginner (default), intermediate, advanced
  --repo <owner/name> Only list issues of this project
  --issue <ref>      Explain one issue directly (owner/repo#123 or an issue URL)
  --limit <n>        Candidate issues to check (default ${CLI_DEFAULT_LIMIT})
  --show-taken       Also list issues that already have an open PR
  --pick <n>         Choose result n without the prompt
  --save             Save the explanation as Markdown
  --no-ai            Do not call Gemini
  --demo             Replay recorded data (no network, no keys)
  --help             Show this help`;

function fail(message: string): never {
  console.error(pc.red(`Error: ${message}`));
  process.exit(1);
}

async function main() {
  const { values } = parseArgs({
    options: {
      lang: { type: 'string' },
      stack: { type: 'string' },
      level: { type: 'string', default: 'beginner' },
      issue: { type: 'string' },
      repo: { type: 'string' },
      limit: { type: 'string', default: String(CLI_DEFAULT_LIMIT) },
      'show-taken': { type: 'boolean', default: false },
      pick: { type: 'string' },
      save: { type: 'boolean', default: false },
      'no-ai': { type: 'boolean', default: false },
      demo: { type: 'boolean', default: false },
      record: { type: 'boolean', default: false },
      help: { type: 'boolean', default: false },
    },
  });
  if (values.help) return console.log(HELP);

  const level = values.level!;
  if (!isValidLevel(level)) fail(`--level must be one of: ${LEVELS.join(', ')}`);
  const limit = Math.max(1, Math.min(CLI_MAX_LIMIT, Number(values.limit) || CLI_DEFAULT_LIMIT));

  const config = loadConfig();
  const mode: FixtureMode = values.demo ? 'replay' : values.record ? 'record' : 'live';
  const fixture: Fixture | undefined =
    mode === 'replay' ? loadFixture(FIXTURE_FILE) :
    mode === 'record' ? { recordedAt: new Date().toISOString(), github: {}, gemini: {} } : undefined;
  const now = fixture ? new Date(fixture.recordedAt).getTime() : Date.now();

  const gh = new GitHubClient(config.githubToken, mode, fixture);
  const useAi = !values['no-ai'] && (mode === 'replay' || Boolean(config.geminiApiKey));
  const ai = config.geminiApiKey && mode !== 'replay' ? new Gemini(config.geminiApiKey, config.modelName) : undefined;

  if (mode === 'replay') console.log(pc.dim(`Demo mode: replaying data recorded ${fixture!.recordedAt.slice(0, 10)}`));
  else if (!gh.hasToken) console.log(pc.yellow('No GITHUB_TOKEN set: limited to 60 GitHub requests/hour and code search is off.'));
  if (!useAi && !values['no-ai']) console.log(pc.yellow('No GEMINI_API_KEY set: showing scores only, no AI explanation.'));

  let issue: Issue;
  let repo: Repository;

  if (values.issue) {
    const ref = parseIssueRef(values.issue);
    if (!ref) fail('--issue must look like owner/repo#123 or a GitHub issue URL');
    [repo, issue] = await Promise.all([fetchRepo(gh, ref.repo), fetchIssue(gh, ref.repo, ref.number)]);
  } else {
    const lang = values.lang ?? values.stack?.split(',')[0];
    if (!lang) fail('Tell me your language: --lang typescript (or --issue owner/repo#123). Try --help.');
    const language = normalizeLanguage(lang);
    if (mode === 'replay') try { assertDemoSupports(fixture, language, level); } catch (e) { fail((e as Error).message); }
    if (fixture && mode === 'record') fixture.meta = { language, level, repo: values.repo };
    let onlyRepos: Repository[] | undefined;
    // The demo recording has one explained project; use it when no --repo is given.
    const wantedRepo = values.repo ?? (mode === 'replay' ? fixture?.meta?.repo : undefined);
    if (wantedRepo) {
      if (!REPO_REF.test(wantedRepo)) fail('--repo must look like owner/name');
      // Also run the project search while recording so the web UI demo can replay its project list.
      if (mode === 'record') await findRepos(gh, language, level as Level, now);
      onlyRepos = [await fetchRepo(gh, wantedRepo)];
    }

    console.log(`\n🔎 Finding ${pc.bold(level)} issues in ${pc.bold(language)} repositories…`);
    const { rows, ratings, hiddenTaken } = await rankIssues({
      gh,
      gemini: useAi ? ai : undefined,
      repos: onlyRepos,
      language,
      level: level as Level,
      limit,
      hideTaken: !values['show-taken'],
      now,
      recordedRatings: mode === 'replay' ? ((fixture!.gemini.difficulty ?? {}) as Record<string, DifficultyResult>) : undefined,
      log: (m) => console.log(`✔ ${m}`),
    });
    if (rows.length === 0) fail(`No free issues found for ${language} at ${level} level (${hiddenTaken} already have an open PR). Try another level.`);
    if (hiddenTaken > 0) console.log(pc.dim(`(${hiddenTaken} issues hidden because they already have an open PR or look fixed; use --show-taken to see them)`));
    if (fixture && mode === 'record') fixture.gemini.difficulty = ratings;
    renderTable(rows);

    let choice = Number(values.pick);
    if (!choice) {
      if (!process.stdin.isTTY) fail('Not an interactive terminal: pass --pick <n>.');
      const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
      choice = Number(await rl.question(`Pick an issue (1-${rows.length}): `));
      rl.close();
    }
    const picked = rows[choice - 1];
    if (!picked) fail(`Pick a number between 1 and ${rows.length}`);
    issue = picked.issue;
    repo = picked.repo;
    if (picked.score.status !== 'Available') {
      console.log(pc.yellow(`Heads up: this issue looks ${picked.score.status.toLowerCase()} (${picked.score.reason}). Consider another one.`));
    }
  }

  if (useAi) console.log(`\n🤖 ${pc.bold('Mentor is exploring')} ${pc.cyan(repo.full_name)}#${issue.number}…`);
  const answer = await explainIssue({
    gh,
    gemini: useAi ? ai : undefined,
    repo,
    issue,
    recordedAnswer:
      mode === 'replay'
        ? issueKey(issue) === fixture!.gemini.mentorFor
          ? String(fixture!.gemini.mentor)
          : `Demo mode only has a recorded explanation for ${fixture!.gemini.mentorFor}. Run without --demo to explain any issue.`
        : undefined,
    onStep: (step) => console.log(pc.dim(`   → ${step}`)),
  });
  if (fixture && mode === 'record') {
    fixture.gemini.mentor = answer;
    fixture.gemini.mentorFor = `${repo.full_name}#${issue.number}`;
  }

  renderMentor(maskSecrets(answer));
  if (values.save) {
    const file = `merge-mentor-${repo.full_name.replace('/', '-')}-${issue.number}.md`;
    saveMarkdown(file, issue, maskSecrets(answer));
    console.log(pc.green(`Saved ${file}`));
  }
  if (mode === 'record' && fixture) {
    saveFixture(FIXTURE_FILE, fixture);
    console.log(pc.green(`Recorded demo data to ${path.relative(process.cwd(), FIXTURE_FILE)}`));
  }
}

main().catch((error) => fail(maskSecrets(error instanceof Error ? error.message : String(error))));
