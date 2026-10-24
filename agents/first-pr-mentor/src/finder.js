// Step 2: find repos and issues in the user's stack with the best chance of a merged PR.
import { scoreRepo, scoreIssue, combine } from "./scoring.js";

const LANGUAGES = {
  typescript: "TypeScript", ts: "TypeScript", javascript: "JavaScript", js: "JavaScript",
  python: "Python", py: "Python", go: "Go", golang: "Go", rust: "Rust", java: "Java",
  kotlin: "Kotlin", ruby: "Ruby", php: "PHP", "c#": "C#", csharp: "C#", "c++": "C++",
  cpp: "C++", swift: "Swift", dart: "Dart", html: "HTML", css: "CSS", vue: "Vue", svelte: "Svelte",
};
const TOPIC_ALIASES = { "next.js": "nextjs", next: "nextjs", "node.js": "nodejs", node: "nodejs", "react.js": "react", reactjs: "react", tailwindcss: "tailwind" };
const BEGINNER_LABEL = /good[\s-]?first[\s-]?issue|first[\s-]?timers?[\s-]?only|beginner|starter|easy/i;

/** Beginner labels, most beginner-specific first ("good first issue" before "easy"). */
export function rankBeginnerLabels(names) {
  const rank = (n) =>
    /good[\s-]?first[\s-]?issue/i.test(n) ? 0 : /first[\s-]?timers?/i.test(n) ? 1 : /beginner|starter/i.test(n) ? 2 : /easy/i.test(n) ? 3 : 9;
  return names.filter((n) => BEGINNER_LABEL.test(n)).sort((a, b) => rank(a) - rank(b));
}

/** "react, Next.js, TS" -> { languages: ["TypeScript"], topics: ["react","nextjs"] } */
export function parseStack(stack) {
  const languages = new Set();
  const topics = new Set();
  for (let raw of String(stack).toLowerCase().split(/[,;/]+|\s+and\s+/)) {
    raw = raw.trim();
    if (!raw) continue;
    if (LANGUAGES[raw] && !["vue", "svelte"].includes(raw)) languages.add(LANGUAGES[raw]);
    else topics.add(TOPIC_ALIASES[raw] || raw.replace(/\s+/g, "-"));
  }
  return { languages: [...languages], topics: [...topics] };
}

function isoDaysAgo(days) {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

export async function findOpportunities(gh, { stack, repoLimit = 4, issuesPerRepo = 3, onProgress = () => {} }) {
  const { languages, topics } = parseStack(stack);
  if (!languages.length && !topics.length) throw new Error("Tell me your stack, e.g. --stack \"react, nextjs, typescript\"");

  // Search once per topic (GitHub ANDs multiple topics, which is too strict).
  const lang = languages[0] ? ` language:${languages[0]}` : "";
  const base = ` good-first-issues:>2 archived:false pushed:>${isoDaysAgo(30)} stars:50..60000`;
  const queries = (topics.length ? topics.slice(0, 3) : [null]).map((t) => (t ? `topic:${t}` : "") + lang + base);

  const seen = new Map();
  for (const q of queries) {
    onProgress(`Searching GitHub: ${q.trim()}`);
    const res = await gh.searchRepos(q.trim(), 10);
    for (const r of res?.items || []) if (!seen.has(r.full_name)) seen.set(r.full_name, r);
  }
  const repos = [...seen.values()].slice(0, repoLimit);
  if (!repos.length) return { languages, topics, results: [] };

  const results = [];
  for (const repo of repos) {
    const full = repo.full_name;
    onProgress(`Checking ${full}: recent PRs, contributor docs, beginner issues`);
    const [pulls, community, labels] = await Promise.all([gh.closedPulls(full), gh.communityProfile(full), gh.labels(full)]);
    const repoScore = scoreRepo({ closedPulls: pulls || [], community, repo });

    // Repos with many labels need a second page.
    let allLabels = labels || [];
    if (allLabels.length === 100) allLabels = allLabels.concat((await gh.labels(full, 2)) || []);
    const beginnerLabels = rankBeginnerLabels(allLabels.map((l) => l.name));

    const issues = [];
    for (const label of beginnerLabels.slice(0, 3)) {
      for (const i of (await gh.openIssuesWithLabel(full, label, 15)) || []) {
        if (!i.pull_request && !i.assignee && !issues.some((x) => x.number === i.number)) issues.push({ ...i, _label: label });
      }
      if (issues.length >= issuesPerRepo) break;
    }

    for (const issue of issues.slice(0, issuesPerRepo)) {
      const label = issue._label;
      onProgress(`Reading the conversation on ${full}#${issue.number}`);
      const [comments, timeline] = await Promise.all([gh.issueComments(full, issue.number), gh.issueTimeline(full, issue.number)]);
      const issueScore = scoreIssue({ issue, comments: comments || [], timeline: timeline || [] });
      const { score, verdict } = combine(repoScore, issueScore);
      results.push({
        ref: `${full}#${issue.number}`,
        repo: full,
        number: issue.number,
        title: issue.title,
        url: issue.html_url,
        stars: repo.stargazers_count,
        label,
        score,
        verdict,
        repoScore,
        issueScore,
      });
    }
  }

  results.sort((a, b) => b.score - a.score);
  return { languages, topics, results };
}
