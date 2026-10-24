import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { redactSensitiveContent } from "./repository-context.js";

const execFileAsync = promisify(execFile);
const MAX_COMMENTS = 15;
const MAX_ISSUE_CHARACTERS = 20_000;
const REF_PATTERN = /^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]{1,100})(?:#|\/issues\/)(\d{1,9})$/;
const URL_PATTERN =
  /^https:\/\/github\.com\/([A-Za-z0-9-]{1,39})\/([A-Za-z0-9._-]{1,100})\/issues\/(\d{1,9})(?:[#?/].*)?$/;

export interface IssueRef {
  owner: string;
  repo: string;
  number: number;
}

export interface GithubIssue {
  ref: IssueRef;
  title: string;
  url: string;
  state: string;
  labels: string[];
  author: string;
  body: string;
  comments: Array<{ author: string; body: string }>;
}

export function parseIssueRef(input: string): IssueRef {
  const trimmed = input.trim();
  const match = REF_PATTERN.exec(trimmed) ?? URL_PATTERN.exec(trimmed);
  if (!match || match[2] === "." || match[2] === "..") {
    throw new Error(
      `Invalid GitHub issue reference "${input}". Use owner/repo#123 or a github.com issue URL.`,
    );
  }
  return { owner: match[1], repo: match[2], number: Number(match[3]) };
}

export function issueToText(issue: GithubIssue): string {
  const comments = issue.comments
    .map((comment) => `--- Comment by @${comment.author} ---\n${comment.body}`)
    .join("\n\n");
  const text = [
    `# ${issue.title}`,
    `Labels: ${issue.labels.join(", ") || "none"}`,
    "",
    issue.body,
    comments,
  ].join("\n");
  return redactSensitiveContent(text).slice(0, MAX_ISSUE_CHARACTERS);
}

async function githubGet<T>(url: string, token?: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "issue-reproduction-assistant",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    const hint = response.status === 403 || response.status === 429
      ? " (rate limited? set GITHUB_TOKEN)"
      : response.status === 404
        ? " (not found or private)"
        : "";
    throw new Error(`GitHub API request failed: ${response.status}${hint}`);
  }
  return (await response.json()) as T;
}

interface RawIssue {
  title: string;
  html_url: string;
  state: string;
  body: string | null;
  user: { login: string } | null;
  labels: Array<string | { name?: string }>;
  pull_request?: unknown;
}
interface RawComment {
  body: string | null;
  user: { login: string } | null;
}

export async function fetchGithubIssue(
  ref: IssueRef,
  token: string | undefined = process.env.GITHUB_TOKEN,
): Promise<GithubIssue> {
  const base = `https://api.github.com/repos/${ref.owner}/${ref.repo}/issues/${ref.number}`;
  const raw = await githubGet<RawIssue>(base, token);
  if (raw.pull_request) {
    throw new Error(`${ref.owner}/${ref.repo}#${ref.number} is a pull request, not an issue.`);
  }
  const comments = await githubGet<RawComment[]>(`${base}/comments?per_page=${MAX_COMMENTS}`, token);

  return {
    ref,
    title: raw.title,
    url: raw.html_url,
    state: raw.state,
    labels: raw.labels.map((label) => (typeof label === "string" ? label : label.name ?? "")).filter(Boolean),
    author: raw.user?.login ?? "unknown",
    body: raw.body ?? "",
    comments: comments
      .filter((comment) => comment.body)
      .map((comment) => ({ author: comment.user?.login ?? "unknown", body: comment.body ?? "" })),
  };
}

export interface ClonedRepository {
  path: string;
  cleanup: () => Promise<void>;
}

/** Shallow, read-only clone for analysis; no repository code is executed. */
export async function cloneRepository(ref: Pick<IssueRef, "owner" | "repo">): Promise<ClonedRepository> {
  const directory = await mkdtemp(path.join(os.tmpdir(), "repro-clone-"));
  const target = path.join(directory, ref.repo);
  try {
    await execFileAsync(
      "git",
      [
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false",
        "clone", "--depth", "100", "--no-tags", "--quiet", "--",
        `https://github.com/${ref.owner}/${ref.repo}.git`,
        target,
      ],
      { env: { ...process.env, GIT_TERMINAL_PROMPT: "0" }, timeout: 120_000 },
    );
  } catch (error) {
    await rm(directory, { recursive: true, force: true });
    throw new Error(`Failed to clone ${ref.owner}/${ref.repo}: ${error instanceof Error ? error.message : error}`);
  }
  return {
    path: target,
    cleanup: () => rm(directory, { recursive: true, force: true }),
  };
}
