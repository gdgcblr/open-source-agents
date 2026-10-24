#!/usr/bin/env node
// first-pr-mentor: find a good first issue, understand it, prove it, then open a PR yourself.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline/promises";
import { parseArgs } from "node:util";

import { createGitHub, RateLimitError } from "./github.js";
import { createGemini } from "./gemini.js";
import { findOpportunities } from "./finder.js";
import { parseRef, gatherContext, explain, explainOffline, gradeAnswer, buildPrKit, sessionMarkdown } from "./mentor.js";
import { c, mark, heading, verdictBadge } from "./ui.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CACHE = join(ROOT, ".mentor-cache", "last-find.json");
const SESSIONS = join(ROOT, "mentor-sessions");
const DEMO = join(ROOT, "fixtures", "demo-github.json");

if (existsSync(join(ROOT, ".env"))) process.loadEnvFile(join(ROOT, ".env"));

const HELP = `
${c.bold("first-pr-mentor")}: your mentor for a first open source PR

  ${c.cyan("start")}                       Guided mode: asks your stack, finds issues, teaches you one
  ${c.cyan("find")} --stack "react, ts"    Rank open beginner issues by chance of getting merged
  ${c.cyan("learn")} <owner/repo#123 | N>  Explain the repo + issue, check your understanding, build the PR kit
  ${c.cyan("explain")} <owner/repo#123 | N> Only the explanation (no quiz)

Options:
  --stack <list>    Your tech stack, comma separated (find/start)
  --level <level>   beginner | intermediate (default: beginner)
  --lang <language> Explain in your language, e.g. kannada, hindi, tamil (default: english)
  --repos <n>       How many repos to check (default: 4)
  --offline         Explain without AI (no Gemini key needed; shallower, no quiz)
  --demo            Replay a recorded GitHub run: no token, no network to GitHub
  --verbose         Show every GitHub request
`;

const { values: opts, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    stack: { type: "string" },
    level: { type: "string", default: "beginner" },
    lang: { type: "string", default: "" },
    repos: { type: "string", default: "4" },
    offline: { type: "boolean", default: false },
    demo: { type: "boolean", default: false },
    record: { type: "string" },
    verbose: { type: "boolean", default: false },
    help: { type: "boolean", short: "h", default: false },
  },
});

const gh = createGitHub({
  token: process.env.GITHUB_TOKEN,
  log: opts.verbose ? (m) => console.log(c.dim(m)) : undefined,
  replay: opts.demo ? DEMO : null,
  record: opts.record || null,
});
if (opts.demo) console.log(c.magenta("DEMO MODE: replaying GitHub data recorded on 2026-10-24 (scores reflect that day).\n"));
const llm = () => createGemini({ apiKey: process.env.GEMINI_API_KEY, model: process.env.GEMINI_MODEL || "gemini-3.8-flash" });
const rl = () => createInterface({ input: process.stdin, output: process.stdout });

function printResults(results) {
  if (!results.length) {
    console.log(c.yellow("No open, unassigned beginner issues found. Try a broader stack (e.g. just \"typescript\")."));
    return;
  }
  results.forEach((r, i) => {
    console.log(`\n${c.bold(`[${i + 1}]`)} ${verdictBadge(r.verdict)} ${c.bold(`${r.score}/100`)}  ${c.cyan(r.ref)}  ${c.dim(`★${r.stars}`)}`);
    console.log(`    ${r.title}`);
    console.log(c.dim(`    ${r.url}`));
    for (const why of [...r.issueScore.reasons, ...r.repoScore.reasons].slice(0, 7)) console.log(`    ${mark(why.ok)} ${why.text}`);
  });
  console.log(c.dim("\nScores are a heuristic from public GitHub data, not a promise. Always read the thread yourself."));
}

async function runFind(stack) {
  heading(`Finding beginner issues for: ${stack}`);
  if (!process.env.GITHUB_TOKEN && !opts.demo) console.log(c.dim("Tip: add a free read-only GITHUB_TOKEN to .env for higher rate limits."));
  const { results } = await findOpportunities(gh, {
    stack,
    repoLimit: Number(opts.repos) || 4,
    onProgress: (m) => console.log(c.dim(`  … ${m}`)),
  });
  mkdirSync(dirname(CACHE), { recursive: true });
  writeFileSync(CACHE, JSON.stringify(results.map((r) => r.ref)));
  printResults(results);
  return results;
}

function resolveRef(arg) {
  if (/^\d+$/.test(arg || "") && existsSync(CACHE)) {
    const refs = JSON.parse(readFileSync(CACHE, "utf8"));
    const ref = refs[Number(arg) - 1];
    if (!ref) throw new Error(`No result #${arg} in your last search.`);
    return parseRef(ref);
  }
  if (!arg) throw new Error("Which issue? e.g. learn vercel/next.js#123, or a number from your last `find`.");
  return parseRef(arg);
}

function printExplanation(ctx, ex) {
  heading(`🚦 Is #${ctx.number} still available?`);
  for (const r of ctx.availability.reasons) console.log(`  ${mark(r.ok)} ${r.text}`);
  if (!ctx.availability.reasons.length) console.log(`  ${mark(true)} No claims, assignees or open PRs found`);
  if (ctx.availability.blocked) console.log(c.red(`  → Probably pick another issue: ${ctx.availability.blocked}.`));

  heading(`📦 ${ctx.repo}: what it is`);
  console.log(ex.what_it_does);
  console.log(c.dim(`Tech: ${(ex.tech_stack || []).join(", ")}`));

  heading("🗺️  Folder map");
  for (const f of ex.folder_map || []) console.log(`  ${c.cyan(f.path.padEnd(24))} ${f.purpose}`);

  heading("▶️  How to run it");
  (ex.how_to_run || []).forEach((s, i) => console.log(`  ${i + 1}. ${s}`));

  heading(`🐛 Issue #${ctx.number} in plain words`);
  console.log(ex.issue_in_plain_words);
  console.log(`${c.bold("Difficulty:")} ${ex.difficulty} ${c.dim(`(${ex.difficulty_reason})`)}`);

  heading("🔎 Where to look");
  if (!ex.likely_files?.length) console.log(c.yellow("  No file names match the issue. Search the code for words from the issue, e.g. `git grep -n \"<keyword>\"`."));
  for (const f of ex.likely_files || []) {
    console.log(`  ${f.verified ? c.green("✔") : c.yellow("?")} ${c.cyan(f.path)}: ${f.why}${f.verified ? "" : c.yellow(" (not found in repo: AI guess)")}`);
  }

  if (ex.concepts_to_learn?.length) {
    heading("📚 Concepts to learn first");
    for (const k of ex.concepts_to_learn) console.log(`  • ${c.bold(k.term)}: ${k.meaning}`);
  }

  heading("👣 First steps");
  (ex.first_steps || []).forEach((s, i) => console.log(`  ${i + 1}. ${s}`));
}

async function quiz(ctx, ex, model) {
  heading("🧠 Understanding check (answer in your own words)");
  console.log(c.dim("Pass 2 of 3 to unlock your PR checklist and draft. Type 'hint' for a nudge.\n"));
  const io = rl();
  const results = [];
  try {
    for (const [i, q] of ex.questions.entries()) {
      let graded = { pass: false };
      let answer = "";
      for (let attempt = 1; attempt <= 2 && !graded.pass; attempt++) {
        answer = await io.question(`${c.bold(`Q${i + 1}.`)} ${q.question}\n${c.magenta("> ")}`);
        if (answer.trim().toLowerCase() === "hint") {
          console.log(c.yellow(`  Hint: ${q.hint}`));
          attempt--;
          continue;
        }
        graded = await gradeAnswer(model, ctx, q, answer, { lang: opts.lang });
        console.log(`  ${mark(graded.pass)} ${graded.feedback}`);
        if (!graded.pass && graded.hint) console.log(c.yellow(`  Hint: ${graded.hint}`));
      }
      results.push({ question: q.question, answer, pass: Boolean(graded.pass), feedback: graded.feedback });
    }
  } finally {
    io.close();
  }
  return results;
}

function printKit(kit) {
  heading("✅ Your PR checklist");
  for (const item of kit.checklist) {
    console.log(`  [ ] ${item.label}`);
    if (item.evidence) console.log(c.dim(`      from ${item.from}: "${item.evidence}"`));
  }
  heading("📝 PR draft (edit before using)");
  console.log(`${c.bold("Title:")} ${kit.prTitle}\n`);
  console.log(kit.prBody);
  console.log(c.dim("\nThe mentor never opens the PR for you. You push your branch and open it yourself."));
}

async function runLearn(arg, { withQuiz = true } = {}) {
  const ref = resolveRef(arg);
  const offline = opts.offline || !process.env.GEMINI_API_KEY;
  console.log(c.dim(`Reading ${ref.repo}#${ref.number}: README, file tree, contributing guide, issue thread…`));
  const ctx = await gatherContext(gh, ref);

  let model = null;
  let ex;
  if (offline) {
    console.log(c.yellow(`Offline mode${opts.offline ? "" : " (no GEMINI_API_KEY in .env)"}: explaining from the repo files only, no AI and no quiz.`));
    ex = explainOffline(ctx);
  } else {
    model = llm();
    console.log(c.dim(`Asking ${model.model} to explain it for a ${opts.level}${opts.lang ? ` in ${opts.lang}` : ""}…`));
    ex = await explain(model, ctx, { level: opts.level, lang: opts.lang });
  }
  printExplanation(ctx, ex);

  let results = null;
  let kit = null;
  if (offline && withQuiz) {
    kit = buildPrKit(ctx, ex, []);
    printKit(kit);
    console.log(c.dim("Add a GEMINI_API_KEY for the full mentor: deeper explanations and the understanding check."));
  } else if (withQuiz && ex.questions?.length) {
    results = await quiz(ctx, ex, model);
    const passed = results.filter((r) => r.pass).length;
    if (passed >= 2) {
      kit = buildPrKit(ctx, ex, results);
      printKit(kit);
    } else {
      heading("🔒 PR kit locked");
      console.log(`You passed ${passed} of 3. Re-read the issue and the files above, then run ${c.cyan(`learn ${ref.repo}#${ref.number}`)} again.`);
      console.log(c.dim("This is on purpose: maintainers merge PRs from people who understand their change."));
    }
  }

  mkdirSync(SESSIONS, { recursive: true });
  const file = join(SESSIONS, `${ref.repo.replace("/", "__")}-${ref.number}.md`);
  writeFileSync(file, sessionMarkdown(ctx, ex, results, kit));
  console.log(`\n${c.green("Saved your notes:")} ${file}`);
}

async function runStart() {
  const io = rl();
  let stack, pick;
  try {
    heading("👋 Welcome to first-pr-mentor");
    stack = opts.stack || (await io.question("What tech do you know? (e.g. react, nextjs, typescript)\n> "));
  } finally {
    io.close();
  }
  const results = await runFind(stack);
  if (!results.length) return;
  const io2 = rl();
  try {
    pick = await io2.question(`\nPick an issue to learn [1-${results.length}] (or Enter to stop): `);
  } finally {
    io2.close();
  }
  if (pick.trim()) await runLearn(pick.trim());
}

async function main() {
  const [cmd, arg] = positionals;
  if (opts.help || !cmd) return console.log(HELP);
  if (cmd === "find") return runFind(opts.stack || arg || "");
  if (cmd === "learn") return runLearn(arg);
  if (cmd === "explain") return runLearn(arg, { withQuiz: false });
  if (cmd === "start") return runStart();
  console.log(HELP);
  process.exitCode = 1;
}

main().catch((err) => {
  console.error(`\n${c.red("Error:")} ${err instanceof RateLimitError ? err.message : err.message || err}`);
  process.exitCode = 1;
});
