#!/usr/bin/env node
import { parseArgs } from 'node:util';
import path from 'node:path';
import readline from 'node:readline/promises';
import pc from 'picocolors';
import { LEVELS, Level, PROJECT_ROOT, isValidLevel, loadConfig, normalizeLanguage } from './config.js';
import { Fixture, FixtureMode, GitHubClient, assertDemoSupports, loadFixture, saveFixture } from './github.js';
import { Issue, Repository, fetchIssue, fetchRepo, parseIssueRef } from './finder.js';
import { DifficultyResult } from './difficulty.js';
import { explainIssue, rankIssues } from './pipeline.js';
import { Gemini } from './gemini.js';
import { maskSecrets } from './mentor.js';
import { renderMentor, renderTable, saveMarkdown } from './render.js';

const FIXTURE_FILE = path.join(PROJECT_ROOT, 'fixtures', 'demo.json');

const HELP = `merge-mentor: from "I know TypeScript" to your first merged PR

Usage:
  merge-mentor --lang <language> [--level beginner|intermediate|advanced]
  merge-mentor --issue owner/repo#123

Options:
  --lang <name>      Language you are good at (e.g. typescript, python, go)
  --level <level>    beginner (default), intermediate, advanced
  --issue <ref>      Explain one issue directly (owner/repo#123 or an issue URL)
  --limit <n>        Candidate issues to check (default 10)
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
      limit: { type: 'string', default: '10' },
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
  const limit = Math.max(1, Math.min(10, Number(values.limit) || 10));

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
    if (fixture && mode === 'record') fixture.meta = { language, level };

    console.log(`\n🔎 Finding ${pc.bold(level)} issues in ${pc.bold(language)} repositories…`);
    const { rows, ratings, hiddenTaken } = await rankIssues({
      gh,
      gemini: useAi ? ai : undefined,
      language,
      level: level as Level,
      limit,
      hideTaken: !values['show-taken'],
      now,
      recordedRatings: mode === 'replay' ? ((fixture!.gemini.difficulty ?? {}) as Record<string, DifficultyResult>) : undefined,
      log: (m) => console.log(`✔ ${m}`),
    });
    if (rows.length === 0) fail(`No free issues found for ${language} at ${level} level (${hiddenTaken} already have an open PR). Try another level.`);
    if (hiddenTaken > 0) console.log(pc.dim(`(${hiddenTaken} issues hidden because they already have an open PR; use --show-taken to see them)`));
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
    recordedAnswer: mode === 'replay' ? String(fixture!.gemini.mentor ?? 'No recorded mentor answer.') : undefined,
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
