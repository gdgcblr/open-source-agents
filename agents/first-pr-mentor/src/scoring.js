// Transparent, rule-based scoring. No AI here: every point comes from
// a GitHub fact, and every fact is shown to the user as a reason.

const DAY = 86_400_000;
const OUTSIDER = new Set(["CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"]);
const FIRST_TIMER = new Set(["FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER"]);
const MAINTAINER = new Set(["OWNER", "MEMBER", "COLLABORATOR"]);

const daysSince = (iso, now) => (now - new Date(iso).getTime()) / DAY;
const median = (xs) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const isBot = (user) => !user || user.type === "Bot" || /\[bot\]$|-bot$|^dependabot|^renovate/i.test(user.login || "");

/**
 * How friendly is this repo to outside contributors, based on its recent PRs?
 * @param {object} input { closedPulls, community, repo, now }
 */
export function scoreRepo({ closedPulls = [], community = null, repo = {}, now = Date.now() }) {
  const reasons = [];
  let score = 0;

  const human = closedPulls.filter((p) => !isBot(p.user));
  const outsiders = human.filter((p) => OUTSIDER.has(p.author_association));
  const merged = outsiders.filter((p) => p.merged_at);
  const firstTimerMerged = merged.filter((p) => FIRST_TIMER.has(p.author_association));

  // 1. Outsider merge rate (35 pts)
  let mergeRate = null;
  if (outsiders.length >= 3) {
    mergeRate = merged.length / outsiders.length;
    score += 35 * mergeRate;
    reasons.push({
      ok: mergeRate >= 0.5 ? true : mergeRate >= 0.25 ? "warn" : false,
      text: `${merged.length} of the last ${outsiders.length} closed PRs from outside contributors were merged (${Math.round(mergeRate * 100)}%)`,
    });
  } else {
    score += 35 * 0.4;
    reasons.push({ ok: "warn", text: `Only ${outsiders.length} recent PRs from outsiders, so the merge rate is uncertain` });
  }

  // 2. Recent merge activity (20 pts)
  const lastMerge = human.filter((p) => p.merged_at).map((p) => daysSince(p.merged_at, now)).sort((a, b) => a - b)[0];
  if (lastMerge === undefined) {
    reasons.push({ ok: false, text: "No human PR merged recently" });
  } else {
    const pts = lastMerge <= 7 ? 1 : lastMerge <= 30 ? 0.7 : lastMerge <= 90 ? 0.3 : 0;
    score += 20 * pts;
    const when = lastMerge < 1 ? "today" : `${Math.round(lastMerge)} day(s) ago`;
    reasons.push({ ok: pts >= 0.7 ? true : pts > 0 ? "warn" : false, text: `Last PR merged ${when}` });
  }

  // 3. Time to merge for outsiders (15 pts)
  const ttm = median(merged.map((p) => (new Date(p.merged_at) - new Date(p.created_at)) / DAY));
  if (ttm !== null) {
    const pts = ttm <= 3 ? 1 : ttm <= 14 ? 0.6 : ttm <= 45 ? 0.3 : 0;
    score += 15 * pts;
    reasons.push({ ok: pts >= 0.6 ? true : "warn", text: `Outsider PRs usually merge in about ${ttm < 1 ? "<1" : Math.round(ttm)} day(s)` });
  }

  // 4. First-timers actually get merged (10 pts)
  if (firstTimerMerged.length) {
    score += 10;
    reasons.push({ ok: true, text: `${firstTimerMerged.length} first-time contributor PR(s) merged recently` });
  }

  // 5. Contributor docs (10 pts)
  const files = community?.files || {};
  if (files.contributing) score += 6;
  if (files.pull_request_template) score += 2;
  if (files.code_of_conduct) score += 2;
  reasons.push({
    ok: files.contributing ? true : "warn",
    text: files.contributing ? "Has a CONTRIBUTING guide" : "No CONTRIBUTING guide (you'll need to ask how they want PRs)",
  });

  // 6. Size sweet spot (10 pts): mid-size repos are easier to land in.
  const stars = repo.stargazers_count ?? 0;
  if (stars >= 50 && stars <= 30000) score += 10;
  else if (stars > 30000) {
    score += 5;
    reasons.push({ ok: "warn", text: `Very popular repo (${stars.toLocaleString()} stars): more competition for beginner issues` });
  } else score += 3;

  if (repo.archived) {
    score = 0;
    reasons.push({ ok: false, text: "Repo is archived (read-only)" });
  }

  return { score: Math.round(score), mergeRate, reasons };
}

const CLAIM_RE =
  /\b(i('| a)?m working on|i am working on|can i (work|take|pick)|could i (work|take)|i('d| would) (like|love) to (work|take|try|contribute)|assign (this|it|me)|i('ll| will) (work|take|pick)|let me (work|take)|please assign)\b/i;
const WELCOME_RE =
  /\b(prs? (is |are )?welcome|feel free to (open|submit|send|make)|happy to (accept|review)|contributions? (are )?welcome|go ahead|sounds good,? (go|feel)|i('ve| have) assigned)\b/i;
const DISCUSS_RE = /\b(needs? (design|discussion|triage|decision|investigation)|rfc|proposal|blocked|wontfix|won't fix|not planned)\b/i;

/**
 * Is this issue a good, still-available pick for a beginner?
 * @param {object} input { issue, comments, timeline, now }
 * @returns {{score:number, blocked:string|null, reasons:Array}}
 */
export function scoreIssue({ issue, comments = [], timeline = [], now = Date.now() }) {
  const reasons = [];
  let score = 50;
  let blocked = null;
  const labels = (issue.labels || []).map((l) => (typeof l === "string" ? l : l.name).toLowerCase());

  // Hard stops
  if (issue.assignee || issue.assignees?.length) {
    blocked = `Already assigned to @${(issue.assignee || issue.assignees[0]).login}`;
  }
  const openPrs = timeline.filter(
    (e) => e.event === "cross-referenced" && e.source?.issue?.pull_request && e.source.issue.state === "open"
  );
  if (openPrs.length) blocked = blocked || `An open PR already references it (#${openPrs[0].source.issue.number})`;

  // Claims in the conversation
  const claims = comments.filter((c) => !MAINTAINER.has(c.author_association) && !isBot(c.user) && CLAIM_RE.test(c.body || ""));
  if (claims.length) {
    const latest = claims[claims.length - 1];
    const age = daysSince(latest.created_at, now);
    if (age <= 30) {
      score -= 30;
      reasons.push({ ok: false, text: `@${latest.user.login} asked to work on it ${Math.round(age)} day(s) ago` });
    } else {
      score -= 5;
      reasons.push({ ok: "warn", text: `@${latest.user.login} asked to work on it ${Math.round(age)} days ago with no PR: politely ask if it's still taken` });
    }
  }

  // Maintainer engagement
  const maint = comments.filter((c) => MAINTAINER.has(c.author_association));
  if (maint.length) {
    score += 15;
    reasons.push({ ok: true, text: `A maintainer has replied in the thread (${maint.length} comment(s))` });
  } else if (comments.length) {
    reasons.push({ ok: "warn", text: "No maintainer reply in the thread yet" });
  }

  // Explicit invitation
  if (labels.some((l) => l.includes("help wanted")) || maint.some((c) => WELCOME_RE.test(c.body || ""))) {
    score += 15;
    reasons.push({ ok: true, text: "Maintainers signal that PRs are welcome" });
  }

  // Needs discussion first: not a beginner task
  if (labels.some((l) => DISCUSS_RE.test(l)) || DISCUSS_RE.test(issue.title || "")) {
    score -= 25;
    reasons.push({ ok: false, text: "Labelled as needing discussion or a decision first" });
  }

  // Clarity
  const body = issue.body || "";
  if (body.length > 200) score += 10;
  if (/```|steps to reproduce|expected behavio/i.test(body)) {
    score += 5;
    reasons.push({ ok: true, text: "Issue has reproduction steps or code examples" });
  }
  if (body.length < 60) reasons.push({ ok: "warn", text: "Very short description: you may need to ask questions first" });

  // Freshness
  const upd = daysSince(issue.updated_at, now);
  if (upd <= 30) score += 10;
  else if (upd <= 90) score += 5;
  else if (upd > 365) {
    score -= 25;
    reasons.push({ ok: false, text: `No activity for ${Math.round(upd)} days: may be outdated or forgotten` });
  } else if (upd > 180) {
    score -= 10;
    reasons.push({ ok: "warn", text: `No activity for ${Math.round(upd)} days` });
  }

  // Long debates are hard for newcomers
  if (comments.length > 15) {
    score -= 10;
    reasons.push({ ok: "warn", text: `Long thread (${comments.length} comments): read it all before starting` });
  }

  if (blocked) reasons.unshift({ ok: false, text: blocked });
  return { score: Math.max(0, Math.min(100, Math.round(score))), blocked, reasons };
}

/** Combine repo + issue into one "chance of merge" number and a verdict. */
export function combine(repoScore, issueScore) {
  if (issueScore.blocked) return { score: 0, verdict: "skip" };
  const score = Math.round(repoScore.score * 0.5 + issueScore.score * 0.5);
  const verdict = score >= 65 ? "good" : score >= 45 ? "maybe" : "risky";
  return { score, verdict };
}
