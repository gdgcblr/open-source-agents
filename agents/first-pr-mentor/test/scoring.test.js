import { test } from "node:test";
import assert from "node:assert/strict";
import { scoreRepo, scoreIssue, combine } from "../src/scoring.js";

const NOW = Date.parse("2026-10-24T00:00:00Z");
const daysAgo = (d) => new Date(NOW - d * 86_400_000).toISOString();
const pr = (assoc, merged, { login = "dev", bot = false, ageDays = 5, mergeDays = 1 } = {}) => ({
  user: { login, type: bot ? "Bot" : "User" },
  author_association: assoc,
  created_at: daysAgo(ageDays + mergeDays),
  merged_at: merged ? daysAgo(ageDays) : null,
});

test("welcoming repo scores high, with reasons", () => {
  const pulls = [
    ...Array.from({ length: 8 }, () => pr("CONTRIBUTOR", true)),
    pr("FIRST_TIME_CONTRIBUTOR", true),
    pr("NONE", false),
  ];
  const r = scoreRepo({ closedPulls: pulls, community: { files: { contributing: {}, pull_request_template: {} } }, repo: { stargazers_count: 2000 }, now: NOW });
  assert.ok(r.score >= 80, `expected >= 80, got ${r.score}`);
  assert.equal(r.mergeRate, 0.9);
  assert.ok(r.reasons.some((x) => x.text.includes("first-time contributor")));
});

test("repo that closes outsider PRs scores low", () => {
  const pulls = Array.from({ length: 10 }, () => pr("NONE", false));
  const r = scoreRepo({ closedPulls: pulls, community: null, repo: { stargazers_count: 2000 }, now: NOW });
  assert.ok(r.score < 30, `expected < 30, got ${r.score}`);
});

test("bot PRs (dependabot) do not inflate the merge rate", () => {
  const pulls = [
    ...Array.from({ length: 20 }, () => pr("NONE", true, { login: "dependabot[bot]", bot: true })),
    ...Array.from({ length: 4 }, () => pr("CONTRIBUTOR", false)),
  ];
  const r = scoreRepo({ closedPulls: pulls, repo: {}, now: NOW });
  assert.equal(r.mergeRate, 0);
});

test("archived repo scores zero", () => {
  assert.equal(scoreRepo({ closedPulls: [], repo: { archived: true }, now: NOW }).score, 0);
});

const issue = (extra = {}) => ({ number: 1, title: "Button has wrong color", body: "x".repeat(300), labels: [{ name: "good first issue" }], updated_at: daysAgo(3), ...extra });

test("assigned issue is blocked", () => {
  const s = scoreIssue({ issue: issue({ assignee: { login: "someone" } }), now: NOW });
  assert.match(s.blocked, /assigned to @someone/);
  assert.equal(combine({ score: 90 }, s).verdict, "skip");
});

test("issue with an open linked PR is blocked", () => {
  const timeline = [{ event: "cross-referenced", source: { issue: { number: 42, state: "open", pull_request: {} } } }];
  const s = scoreIssue({ issue: issue(), timeline, now: NOW });
  assert.match(s.blocked, /#42/);
});

test("recent claim in the conversation lowers the score", () => {
  const comments = [{ user: { login: "newbie" }, author_association: "NONE", body: "Can I work on this?", created_at: daysAgo(2) }];
  const free = scoreIssue({ issue: issue(), now: NOW }).score;
  const claimed = scoreIssue({ issue: issue(), comments, now: NOW });
  assert.ok(claimed.score <= free - 30);
  assert.ok(claimed.reasons.some((r) => r.text.includes("@newbie")));
});

test("maintainer invitation raises the score", () => {
  const comments = [{ user: { login: "maint" }, author_association: "MEMBER", body: "PRs welcome!", created_at: daysAgo(1) }];
  const s = scoreIssue({ issue: issue(), comments, now: NOW });
  assert.ok(s.reasons.some((r) => r.text.includes("PRs are welcome")));
  assert.ok(s.score >= 90);
});

test("very stale issue is flagged", () => {
  const s = scoreIssue({ issue: issue({ updated_at: daysAgo(800) }), now: NOW });
  assert.ok(s.reasons.some((r) => r.ok === false && r.text.includes("800 days")));
});

test("combine gives a verdict", () => {
  assert.equal(combine({ score: 80 }, { score: 80, blocked: null }).verdict, "good");
  assert.equal(combine({ score: 50 }, { score: 50, blocked: null }).verdict, "maybe");
  assert.equal(combine({ score: 20 }, { score: 30, blocked: null }).verdict, "risky");
});
