// Turns a repo's CONTRIBUTING guide and PR template into a checklist.
// Deterministic keyword detectors, so the same repo always gives the same
// checklist, and each item quotes the sentence it came from.

const DETECTORS = [
  { id: "issue-first", label: "Open or comment on an issue before sending a PR", re: /(open|create|file) an issue (first|before)|discuss(ed)? .{0,40}before .{0,30}(pr|pull request)|before (starting|submitting|opening) .{0,40}(open|create) an issue/i },
  { id: "dco", label: "Sign off every commit (git commit -s)", re: /signed-off-by|developer certificate of origin|\bDCO\b|git commit -s\b/i },
  { id: "cla", label: "Sign the Contributor License Agreement (CLA)", re: /\bCLA\b|contributor license agreement/i },
  { id: "conventional", label: "Use Conventional Commit messages (feat:, fix:, docs:)", re: /conventional commits?|commitlint|semantic commit/i },
  { id: "tests", label: "Add or update tests for your change", re: /(add|include|write) (unit |new )?tests|tests? (are|is) required|must (include|have) tests|test coverage/i },
  { id: "changeset", label: "Add a changeset (npx changeset)", re: /changesets?\b/i },
  { id: "lint", label: "Run the linter/formatter before pushing", re: /(npm|pnpm|yarn|bun) (run )?(lint|format)|prettier|eslint|ruff|black\b|gofmt|cargo fmt/i },
  { id: "small-pr", label: "Keep the PR small and focused on one change", re: /small(er)?,? (and )?(focused )?(prs?|pull requests?)|one (change|feature|fix|thing) per (pr|pull request)|keep (your )?(prs?|pull requests?) (small|focused)/i },
  { id: "screenshots", label: "Add screenshots or a recording for UI changes", re: /screenshots?|screen recording|gif/i },
  { id: "ai-policy", label: "Follow the repo's AI-use policy (disclose AI help)", re: /\b(ai|llm|copilot|chatgpt|claude|gemini|generative)\b[^.\n]{0,80}\b(disclos|must|not (be )?(allowed|accepted)|prohibit|policy|generated)/i },
];

/** Return the sentence around a match so users can see why a rule applies. */
function evidence(text, re) {
  const m = text.match(re);
  if (!m) return null;
  const start = Math.max(0, text.lastIndexOf("\n", m.index) + 1);
  let end = text.indexOf("\n", m.index + m[0].length);
  if (end === -1) end = text.length;
  return text.slice(start, end).replace(/^[\s#>*-]+/, "").trim().slice(0, 180);
}

export function extractRules({ contributing = "", prTemplate = "", aiPolicy = "" } = {}) {
  const text = [contributing, aiPolicy].join("\n");
  const rules = [];
  for (const d of DETECTORS) {
    const ev = evidence(text, d.re);
    if (ev) rules.push({ id: d.id, label: d.label, evidence: ev });
  }

  const base = text.match(/branch(es)? (off|from) (of )?`?(main|master|develop|dev|canary|next)`?/i);
  if (base) rules.push({ id: "base-branch", label: `Create your branch from \`${base[4]}\``, evidence: evidence(text, /branch(es)? (off|from)/i) });

  if (aiPolicy && !rules.some((r) => r.id === "ai-policy")) {
    rules.push({ id: "ai-policy", label: "Read the repo's AI-use policy file before using AI help", evidence: "Repo has a dedicated AI policy file" });
  }

  // Sections the PR description must fill, taken from the template headings.
  const templateSections = [...prTemplate.matchAll(/^#{1,4}\s+(.+)$/gm)].map((m) => m[1].trim()).slice(0, 10);
  const templateChecks = [...prTemplate.matchAll(/^\s*[-*]\s+\[ \]\s+(.+)$/gm)].map((m) => m[1].trim()).slice(0, 12);

  return { rules, templateSections, templateChecks };
}
