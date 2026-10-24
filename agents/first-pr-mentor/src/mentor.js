// Steps 3 and 4: explain the repo + issue, check understanding, build the PR kit.
import { untrusted } from "./gemini.js";
import { extractRules } from "./rules.js";
import { scoreIssue } from "./scoring.js";

const langLine = (lang) =>
  lang && !/^english$/i.test(lang)
    ? `\nWrite every text value in ${lang}, in simple everyday words. Keep code, file paths, commands and JSON keys in English.\n`
    : "";

const SKIP_PATH = /(^|\/)(node_modules|dist|build|out|\.next|vendor|coverage|\.git)(\/|$)|\.(png|jpe?g|gif|svg|ico|webp|mp4|woff2?|ttf|lock)$|(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$/i;

export function parseRef(ref) {
  const m = String(ref).trim().match(/^(?:https:\/\/github\.com\/)?([\w.-]+\/[\w.-]+)(?:#|\/issues\/)(\d+)$/);
  if (!m) throw new Error(`Use the form owner/repo#123 (got "${ref}")`);
  return { repo: m[1], number: Number(m[2]) };
}

/** Paths the issue links to (github blob links) that no longer exist: a strong sign the issue is outdated. */
export function missingMentionedFiles(body, paths) {
  const real = new Set(paths);
  const linked = [...String(body || "").matchAll(/github\.com\/[\w.-]+\/[\w.-]+\/blob\/[^/\s]+\/([^\s)#?"']+)/g)].map((m) => decodeURIComponent(m[1]));
  return [...new Set(linked)].filter((p) => !real.has(p));
}

function withMovedFiles(availability, issue, treeRes) {
  const paths = (treeRes?.tree || []).map((t) => t.path);
  if (!paths.length || treeRes?.truncated) return availability;
  const gone = missingMentionedFiles(issue?.body, paths);
  if (gone.length) {
    availability.reasons.push({ ok: false, text: `The issue links to ${gone.slice(0, 2).map((p) => `\`${p}\``).join(", ")}, which no longer exists: the code was probably moved or rewritten` });
  }
  return availability;
}

/** Collect everything the mentor is allowed to read: README, tree, docs, issue thread. */
export async function gatherContext(gh, { repo, number }) {
  const meta = await gh.repo(repo);
  if (!meta) throw new Error(`Repo ${repo} not found (or it is private).`);
  const [issue, comments, timeline, readme, treeRes] = await Promise.all([
    gh.issue(repo, number),
    gh.issueComments(repo, number),
    gh.issueTimeline(repo, number),
    gh.readme(repo),
    gh.tree(repo, meta.default_branch),
  ]);
  if (!issue) throw new Error(`Issue #${number} not found in ${repo}.`);
  if (issue.pull_request) throw new Error(`#${number} is a pull request, not an issue.`);

  const paths = (treeRes?.tree || []).filter((t) => t.type === "blob").map((t) => t.path);
  const find = (re) => paths.find((p) => re.test(p));
  const contributingPath = find(/(^|\/)contributing(\.md|\.rst|\.txt)?$/i);
  const templatePath = find(/(^|\/)pull_request_template\.md$/i);
  const aiPolicyPath = find(/(^|\/)(ai[-_]?(policy|usage|contributions?)|ai_policy)(\.md)?$/i);

  const [contributing, prTemplate, aiPolicy] = await Promise.all([
    contributingPath ? gh.file(repo, contributingPath) : "",
    templatePath ? gh.file(repo, templatePath) : "",
    aiPolicyPath ? gh.file(repo, aiPolicyPath) : "",
  ]);

  return {
    repo,
    number,
    meta,
    issue,
    comments: comments || [],
    // Same rules as `find`: is the issue still free to take?
    availability: withMovedFiles(scoreIssue({ issue, comments: comments || [], timeline: timeline || [] }), issue, treeRes),
    readme: readme || "",
    paths,
    treeTruncated: Boolean(treeRes?.truncated),
    contributing: contributing || "",
    contributingPath,
    prTemplate: prTemplate || "",
    aiPolicy: aiPolicy || "",
    aiPolicyPath,
  };
}

function treeSummary(paths, max = 350) {
  const useful = paths.filter((p) => !SKIP_PATH.test(p));
  const dirs = new Set();
  for (const p of useful) {
    const parts = p.split("/");
    if (parts.length > 1) dirs.add(parts.slice(0, Math.min(2, parts.length - 1)).join("/") + "/");
  }
  return { dirs: [...dirs].slice(0, 80), files: useful.slice(0, max), total: paths.length };
}

function threadText(issue, comments) {
  const lines = [`#${issue.number} ${issue.title}`, `opened by @${issue.user?.login}`, "", issue.body || "(no description)"];
  for (const c of comments.slice(-15)) {
    lines.push("", `--- @${c.user?.login} (${c.author_association}) on ${c.created_at.slice(0, 10)}:`, (c.body || "").slice(0, 1200));
  }
  return lines.join("\n");
}

/** One Gemini call: plain-language explanation of the repo + issue, and 3 check questions. */
export async function explain(llm, ctx, { level = "beginner", lang = "" } = {}) {
  const tree = treeSummary(ctx.paths);
  const prompt = `A ${level} wants to fix this GitHub issue. Help them understand the project and the issue.
${langLine(lang)}
Repository: ${ctx.repo} (${ctx.meta.language || "unknown language"}, ${ctx.meta.stargazers_count} stars)
Description: ${ctx.meta.description || "none"}
Top folders: ${tree.dirs.join(", ")}
Files (${tree.total} total${ctx.treeTruncated ? ", list truncated by GitHub" : ""}, showing ${tree.files.length}):
${tree.files.join("\n")}

${untrusted("README", ctx.readme, 5000)}

${untrusted("CONTRIBUTING", ctx.contributing, 3000)}

${untrusted("issue thread", threadText(ctx.issue, ctx.comments), 7000)}

Return JSON with exactly these keys:
{
  "what_it_does": "2-3 sentences, plain words",
  "tech_stack": ["main technologies, max 6"],
  "folder_map": [{"path": "folder/", "purpose": "one line"}],  // 4-8 most important folders
  "how_to_run": ["setup step", "..."],                          // from README/CONTRIBUTING; say if unknown
  "issue_in_plain_words": "what is wrong or wanted, and what 'done' looks like",
  "likely_files": [{"path": "exact path from the file list", "why": "one line"}],  // 1-5, ONLY paths from the list above
  "concepts_to_learn": [{"term": "...", "meaning": "one simple sentence"}],      // 2-5
  "difficulty": "easy | medium | hard",
  "difficulty_reason": "one line",
  "first_steps": ["concrete beginner step", "..."],              // 3-6, ends with commenting on the issue before coding
  "questions": [                                                 // exactly 3 questions that check real understanding
    {"question": "...", "good_answer_covers": "key points a correct answer mentions", "hint": "a nudge, not the answer"}
  ]
}`;
  const out = await llm.generate(prompt, { json: true });

  // Guardrail against hallucinated paths: mark any file that isn't really in the repo.
  const real = new Set(ctx.paths);
  out.likely_files = (out.likely_files || []).map((f) => ({ ...f, verified: real.has(f.path) }));
  out.questions = (out.questions || []).slice(0, 3);
  return out;
}

const FOLDER_PURPOSE = [
  [/^(src|lib|source)\/$/i, "Main source code"],
  [/^(packages|apps|libs|modules)\/$/i, "Monorepo: each sub-folder is its own package or app"],
  [/^(test|tests|__tests__|spec|e2e|cypress|playwright)\/$/i, "Automated tests"],
  [/^(docs?|documentation|website|site)\/$/i, "Documentation"],
  [/^(examples?|demo|demos|samples?|playground|sandbox)\/$/i, "Example projects that use the library"],
  [/^(scripts?|tools|bin)\/$/i, "Helper scripts for building and maintaining the project"],
  [/^\.github\/$/i, "GitHub settings: CI workflows, issue and PR templates"],
  [/^(public|static|assets)\/$/i, "Static files (images, fonts)"],
  [/^(components?|ui)\/$/i, "UI components"],
  [/^(app|pages)\/$/i, "App routes or pages"],
  [/^(config|configs)\/$/i, "Configuration"],
];
const STACK_HINTS = [
  [/(^|\/)package\.json$/, "Node.js"], [/(^|\/)tsconfig[\w.]*\.json$/, "TypeScript"], [/(^|\/)next\.config\./, "Next.js"],
  [/(^|\/)vite\.config\./, "Vite"], [/\.(jsx|tsx)$/, "React (JSX)"], [/(^|\/)(requirements\.txt|pyproject\.toml)$/, "Python"],
  [/(^|\/)go\.mod$/, "Go"], [/(^|\/)Cargo\.toml$/, "Rust"], [/(^|\/)pnpm-workspace\.yaml$/, "pnpm workspaces"],
  [/(^|\/)turbo\.json$/, "Turborepo"], [/(^|\/)Dockerfile$/, "Docker"], [/\.vue$/, "Vue"], [/\.svelte$/, "Svelte"],
];
const STOP = new Set("when with this that from have does should into after before using used about there their which while issue error fails broken support allow added update when".split(" "));

/** Commands from fenced code blocks that look like setup/run/test steps. */
export function setupCommands(...docs) {
  const cmds = [];
  for (const doc of docs) {
    for (const block of String(doc || "").matchAll(/```(?:bash|sh|shell|console|zsh|powershell)?\n([\s\S]*?)```/g)) {
      for (let line of block[1].split("\n")) {
        line = line.replace(/^\$\s*/, "").trim();
        if (/^(git clone|cd |npm |pnpm |yarn |bun |npx |pip |python|poetry |uv |go |cargo |make|docker)/.test(line) && !cmds.includes(line)) cmds.push(line);
      }
    }
  }
  return cmds.slice(0, 8);
}

/** Files whose names share words with the issue title. Every result is a real path. */
export function likelyFilesOffline(title, paths) {
  const words = (title.toLowerCase().match(/[a-z][a-z0-9]{3,}/g) || []).filter((w) => !STOP.has(w));
  const scored = paths
    .filter((p) => !SKIP_PATH.test(p) && !/(^|\/)(test|tests|__tests__|docs?)\//i.test(p))
    .map((p) => {
      const name = p.toLowerCase();
      const base = name.split("/").pop();
      return { path: p, hits: words.filter((w) => base.includes(w)).length * 2 + words.filter((w) => name.includes(w)).length };
    })
    .filter((x) => x.hits > 0)
    .sort((a, b) => b.hits - a.hits || a.path.length - b.path.length);
  return scored.slice(0, 5).map((x) => ({ path: x.path, why: "File name matches words in the issue title", verified: true }));
}

/** Explanation without any AI: works with no Gemini key. Shallower, but never invents anything. */
export function explainOffline(ctx) {
  const tree = treeSummary(ctx.paths);
  const top = [...new Set(ctx.paths.filter((p) => p.includes("/")).map((p) => p.split("/")[0] + "/"))].filter((d) => !d.startsWith(".") || d === ".github/");
  const firstPara = (ctx.readme.split(/\n\s*\n/).find((p) => /[a-z]{4,}/i.test(p) && !/^\s*(#|!\[|<|\[!\[)/.test(p)) || "").replace(/\s+/g, " ").trim();
  const stack = [ctx.meta.language, ...STACK_HINTS.filter(([re]) => ctx.paths.some((p) => re.test(p))).map(([, n]) => n)].filter(Boolean);
  const cmds = setupCommands(ctx.contributing, ctx.readme);
  const labels = (ctx.issue.labels || []).map((l) => l.name.toLowerCase());
  const easy = labels.some((l) => /good first|first-timer|beginner|easy|docs?|documentation|typo/.test(l));

  return {
    offline: true,
    what_it_does: [ctx.meta.description, firstPara.slice(0, 400)].filter(Boolean).join(" ") || "No description found in the README.",
    tech_stack: [...new Set(stack)].slice(0, 6),
    folder_map: top.slice(0, 10).map((d) => ({ path: d, purpose: FOLDER_PURPOSE.find(([re]) => re.test(d))?.[1] || `${ctx.paths.filter((f) => f.startsWith(d)).length} files` })),
    how_to_run: cmds.length ? cmds : ["No setup commands found in README/CONTRIBUTING. Look for a 'Development' or 'Getting started' section."],
    issue_in_plain_words: `${ctx.issue.title}. ${(ctx.issue.body || "").replace(/<!--[\s\S]*?-->/g, "").replace(/\s+/g, " ").trim().slice(0, 350)}`,
    likely_files: likelyFilesOffline(ctx.issue.title, ctx.paths),
    concepts_to_learn: [],
    difficulty: easy ? "easy" : "unknown",
    difficulty_reason: easy ? "labelled as beginner-friendly by maintainers" : "no beginner label; read the thread carefully",
    first_steps: [
      "Read the whole issue thread, including every comment",
      ctx.contributingPath ? `Read ${ctx.contributingPath}` : "Look for contribution rules in the README",
      "Fork the repo, clone it, and get it running with the commands above",
      "Reproduce the problem (or find where the feature would go) before changing code",
      "Comment on the issue with your plan and wait for a maintainer's OK",
    ],
    questions: [],
  };
}

/** Grade one answer. Short or empty answers fail without spending an API call. */
export async function gradeAnswer(llm, ctx, q, answer, { lang = "" } = {}) {
  if (!answer || answer.trim().split(/\s+/).length < 5) {
    return { pass: false, feedback: "Please answer in at least one full sentence, in your own words.", hint: q.hint };
  }
  const prompt = `You are checking whether a beginner understands an issue before they code. Be encouraging but honest.
The learner may answer in any language.${langLine(lang)}
Issue: ${ctx.repo}#${ctx.number} "${ctx.issue.title}"
Question: ${q.question}
A good answer covers: ${q.good_answer_covers}
${untrusted("learner answer", answer, 1500)}

Return JSON: {"pass": true|false, "feedback": "1-2 sentences on what they got right or missed", "hint": "if not passed, a nudge that does not give away the answer, else empty"}
Pass if the main idea is right even if the wording is rough.`;
  return llm.generate(prompt, { json: true, temperature: 0.2 });
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);

/** Build the PR kit: checklist from the repo's real rules + a PR description from the learner's own answers. */
export function buildPrKit(ctx, explanation, answers) {
  const { rules, templateSections, templateChecks } = extractRules(ctx);
  const branch = `fix/${ctx.number}-${slug(ctx.issue.title)}`;

  const checklist = [
    { label: `Comment on the issue that you'd like to work on it, and wait for a maintainer's OK`, from: "mentor" },
    { label: `Fork ${ctx.repo} and create a branch: \`git checkout -b ${branch}\``, from: "mentor" },
    ...rules.map((r) => ({ label: r.label, from: ctx.contributingPath || "repo docs", evidence: r.evidence })),
    ...templateChecks.map((c) => ({ label: c, from: "PR template" })),
    { label: "Run the project and its tests locally before pushing", from: "mentor" },
    { label: `Link the issue in the PR description ("Fixes #${ctx.number}")`, from: "mentor" },
    { label: "Read your own diff line by line; you must be able to explain every change", from: "mentor" },
  ];

  const answerBlock = answers.length
    ? answers.map((a) => `- ${a.answer.trim()}`).join("\n")
    : "<!-- In your own words: what was wrong, what you changed, and why. -->";
  const sections = templateSections.length ? templateSections : ["What does this PR do?", "How did you test it?"];
  const body = [
    `Fixes #${ctx.number}`,
    "",
    ...sections.flatMap((s, i) => [
      `## ${s}`,
      i === 0 ? `<!-- Your own understanding, from the mentor check. Edit it to match what you actually changed. -->\n${answerBlock}` : "<!-- fill in -->",
      "",
    ]),
    "## AI assistance",
    "I used an AI mentor (first-pr-mentor) to understand the codebase. I wrote and reviewed the code changes myself and can explain every line.",
  ].join("\n");

  return {
    branch,
    checklist,
    rulesFound: rules.length,
    prTitle: `fix: ${ctx.issue.title.replace(/^\[?(bug|feature|docs?)\]?:?\s*/i, "").slice(0, 70)} (#${ctx.number})`,
    prBody: body,
  };
}

/** Markdown report saved for the learner, so they can come back to it. */
export function sessionMarkdown(ctx, ex, results, kit) {
  const L = [];
  L.push(`# ${ctx.repo}#${ctx.number}: ${ctx.issue.title}`, "", `Issue: ${ctx.issue.html_url}`, "");
  if (ctx.availability) {
    L.push("## Is it still available?", ...ctx.availability.reasons.map((r) => `- ${r.ok === true ? "✅" : r.ok === "warn" ? "⚠️" : "❌"} ${r.text}`), "");
  }
  L.push("## What the project does", ex.what_it_does, "", `**Tech:** ${(ex.tech_stack || []).join(", ")}`, "");
  L.push("## Folder map", ...(ex.folder_map || []).map((f) => `- \`${f.path}\`: ${f.purpose}`), "");
  L.push("## How to run it", ...(ex.how_to_run || []).map((s, i) => `${i + 1}. ${s}`), "");
  L.push("## The issue in plain words", ex.issue_in_plain_words, "", `**Difficulty:** ${ex.difficulty} (${ex.difficulty_reason})`, "");
  L.push("## Where to look", ...(ex.likely_files || []).map((f) => `- \`${f.path}\`${f.verified ? "" : " (not found in repo, AI guess)"}: ${f.why}`), "");
  L.push("## Concepts to learn first", ...(ex.concepts_to_learn || []).map((c) => `- **${c.term}**: ${c.meaning}`), "");
  L.push("## First steps", ...(ex.first_steps || []).map((s, i) => `${i + 1}. ${s}`), "");
  if (results?.length) {
    L.push("## Understanding check", ...results.map((r) => `- ${r.pass ? "✅" : "❌"} ${r.question}\n  - Your answer: ${r.answer}\n  - Feedback: ${r.feedback}`), "");
  }
  if (kit) {
    L.push("## PR checklist", ...kit.checklist.map((c) => `- [ ] ${c.label}${c.evidence ? `  \n  _from ${c.from}: "${c.evidence}"_` : ""}`), "");
    L.push("## PR draft", `**Title:** ${kit.prTitle}`, "", "```markdown", kit.prBody, "```", "");
  }
  L.push("---", "_Generated by first-pr-mentor. AI explanations can be wrong: verify in the code and ask maintainers when unsure._");
  return L.join("\n");
}
