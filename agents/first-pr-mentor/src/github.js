// Read-only GitHub REST client.
// Guardrail: this module only ever sends GET requests. The mentor never
// comments, forks, opens PRs or changes anything on GitHub for the user.
//
// Responses are trimmed to the fields the mentor uses. That keeps memory low
// and lets a whole run be recorded to a small JSON file and replayed offline
// (`--demo`), with no token and no rate limit.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const API = "https://api.github.com";

export class RateLimitError extends Error {}

const cut = (s, n) => (typeof s === "string" ? s.slice(0, n) : s);
const user = (u) => (u ? { login: u.login, type: u.type } : null);
const labelNames = (ls) => (ls || []).map((l) => ({ name: typeof l === "string" ? l : l.name }));

const slim = {
  search: (r) => ({ items: (r?.items || []).map(slim.repo) }),
  repo: (r) =>
    r && {
      full_name: r.full_name, description: r.description, language: r.language, default_branch: r.default_branch,
      stargazers_count: r.stargazers_count, archived: r.archived, html_url: r.html_url,
    },
  pulls: (ps) => (ps || []).map((p) => ({ user: user(p.user), author_association: p.author_association, created_at: p.created_at, merged_at: p.merged_at })),
  community: (c) => c && { files: Object.fromEntries(Object.entries(c.files || {}).filter(([, v]) => v).map(([k]) => [k, {}])) },
  issue: (i) =>
    i && {
      number: i.number, title: i.title, body: cut(i.body, 4000), html_url: i.html_url, state: i.state,
      labels: labelNames(i.labels), assignee: user(i.assignee), assignees: (i.assignees || []).map(user),
      updated_at: i.updated_at, created_at: i.created_at, user: user(i.user), pull_request: i.pull_request ? {} : undefined,
    },
  issues: (is) => (is || []).map(slim.issue),
  comments: (cs) => (cs || []).map((c) => ({ user: user(c.user), author_association: c.author_association, body: cut(c.body, 1500), created_at: c.created_at })),
  timeline: (es) =>
    (es || [])
      .filter((e) => e.event === "cross-referenced" || e.event === "assigned" || e.event === "closed")
      .map((e) => ({
        event: e.event,
        source: e.source?.issue ? { issue: { number: e.source.issue.number, state: e.source.issue.state, pull_request: e.source.issue.pull_request ? {} : undefined } } : undefined,
      })),
  labels: (ls) => labelNames(ls),
  tree: (t) => t && { truncated: t.truncated, tree: (t.tree || []).filter((x) => x.type === "blob").slice(0, 4000).map((x) => ({ path: x.path, type: x.type })) },
  text: (s) => cut(s, 12000),
};

export function createGitHub({ token, log = () => {}, record = null, replay = null } = {}) {
  let remaining = null;
  // Recording appends to an existing file, so `find` and `learn` can share one demo file.
  const recorded = record && existsSync(record) ? JSON.parse(readFileSync(record, "utf8")) : {};
  const fixture = replay ? JSON.parse(readFileSync(replay, "utf8")) : null;

  async function fetchGet(path, accept, raw) {
    const headers = { Accept: accept, "User-Agent": "first-pr-mentor", "X-GitHub-Api-Version": "2022-11-28" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API}${path}`, { method: "GET", headers });

    const left = res.headers.get("x-ratelimit-remaining");
    if (left !== null) remaining = Number(left);
    if (res.status === 403 || res.status === 429) {
      const reset = Number(res.headers.get("x-ratelimit-reset") || 0) * 1000;
      const mins = reset ? Math.max(1, Math.ceil((reset - Date.now()) / 60000)) : "a few";
      throw new RateLimitError(
        `GitHub rate limit reached. Try again in ${mins} minute(s)` +
          (token ? "." : ", add a free read-only GITHUB_TOKEN to .env, or try the offline demo: --demo")
      );
    }
    if (res.status === 404 || res.status === 409) return null; // 409 = empty repo
    if (!res.ok) throw new Error(`GitHub ${res.status} for ${path}`);
    log(`GET ${path} (rate left: ${remaining ?? "?"})`);
    return raw ? res.text() : res.json();
  }

  async function get(path, shape, { accept = "application/vnd.github+json", raw = false } = {}) {
    if (fixture) {
      if (!(path in fixture)) throw new Error(`Not in the demo data: ${path}. The demo only covers the recorded run (see README).`);
      return fixture[path];
    }
    const data = shape(await fetchGet(path, accept, raw));
    if (record) {
      recorded[path] = data;
      writeFileSync(record, JSON.stringify(recorded));
    }
    return data;
  }

  const RAW = { accept: "application/vnd.github.raw", raw: true };

  return {
    get remaining() {
      return remaining;
    },
    searchRepos: (query, perPage = 10) => get(`/search/repositories?q=${encodeURIComponent(query)}&per_page=${perPage}`, slim.search),
    repo: (full) => get(`/repos/${full}`, slim.repo),
    // Closed PRs include merged ones (merged_at set) and rejected ones.
    closedPulls: (full, n = 50) => get(`/repos/${full}/pulls?state=closed&sort=updated&direction=desc&per_page=${n}`, slim.pulls),
    communityProfile: (full) => get(`/repos/${full}/community/profile`, slim.community),
    openIssuesWithLabel: (full, label, n = 15) =>
      get(`/repos/${full}/issues?state=open&labels=${encodeURIComponent(label)}&sort=updated&direction=desc&per_page=${n}`, slim.issues),
    issue: (full, num) => get(`/repos/${full}/issues/${num}`, slim.issue),
    issueComments: (full, num, n = 50) => get(`/repos/${full}/issues/${num}/comments?per_page=${n}`, slim.comments),
    // Timeline shows cross-references, e.g. a PR that mentions the issue.
    issueTimeline: (full, num) => get(`/repos/${full}/issues/${num}/timeline?per_page=100`, slim.timeline),
    labels: (full, page = 1) => get(`/repos/${full}/labels?per_page=100&page=${page}`, slim.labels),
    readme: (full) => get(`/repos/${full}/readme`, slim.text, RAW),
    tree: (full, branch) => get(`/repos/${full}/git/trees/${encodeURIComponent(branch)}?recursive=1`, slim.tree),
    file: (full, path) => get(`/repos/${full}/contents/${path.split("/").map(encodeURIComponent).join("/")}`, slim.text, RAW),
  };
}

export const fixtureExists = (p) => existsSync(p);
