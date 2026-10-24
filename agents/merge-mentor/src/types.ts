/**
 * Every shared type in one place, so the rest of the code can stay about behaviour.
 * Grouped by what they describe: configuration, GitHub data, scoring, the AI side, and the pipeline.
 */
import type { Gemini } from './ai/gemini.js';
import type { GitHubClient } from './github/client.js';

// ---- Configuration -----------------------------------------------------------------------------

export type Level = 'beginner' | 'intermediate' | 'advanced';

export interface Config {
  geminiApiKey?: string;
  modelName: string;
  githubToken?: string;
}

export interface LevelProfile {
  labels: string[];
  repoQualifier: string;
  targetDifficulty: number;
}

// ---- GitHub data -------------------------------------------------------------------------------

export interface Repository {
  full_name: string;
  stargazers_count: number;
  pushed_at: string;
  default_branch: string;
  language: string | null;
  description?: string | null;
  html_url?: string;
}

export interface Issue {
  number: number;
  title: string;
  html_url: string;
  body: string | null;
  comments: number;
  created_at: string;
  updated_at: string;
  labels: { name: string }[];
  repo_full_name: string;
}

// ---- Scoring: is an issue free, and is the project welcoming? ----------------------------------

/** Available: free. Claimed: someone asked recently. Taken: an open PR exists. Fixed: a merged PR already references it. */
export type ClaimStatus = 'Available' | 'Claimed' | 'Taken' | 'Fixed';

export interface ClaimResult {
  status: ClaimStatus;
  reason?: string;
}

export interface RepoHealth {
  closedPRs: number;
  mergedPRs: number;
  outsideMerged: number;
  medianDaysToMerge: number | null;
}

export interface ScoreResult extends ClaimResult {
  score: number;
  health: RepoHealth;
}

export interface DifficultyResult {
  difficulty: number; // 1 (trivial) - 5 (hard)
  reason: string;
}

export interface Row {
  issue: Issue;
  repo: Repository;
  score: ScoreResult;
  difficulty?: DifficultyResult;
}

// ---- Recorded demo data ------------------------------------------------------------------------

export type FixtureMode = 'live' | 'record' | 'replay';

/** Recorded responses used by --demo (replay) and --record. */
export interface Fixture {
  recordedAt: string;
  /** The one search the recording covers; demo mode refuses anything else. */
  meta?: { language: string; level: string; repo?: string; repos?: string[] };
  github: Record<string, unknown>;
  gemini: Record<string, unknown>;
}

// ---- Checks on the AI answer -------------------------------------------------------------------

export interface ReadRecord {
  /** Full text of the file. */
  text: string;
  /** Line ranges that were actually shown to the model (1-based, inclusive). */
  ranges: [number, number][];
}

/** path -> what the agent read from it during one mentor run. */
export type ReadLog = Map<string, ReadRecord>;

export interface Citation {
  path: string;
  from: number;
  to: number;
}

export interface CitationCheck {
  total: number;
  verified: number;
  problems: string[];
}

export interface DiffCheck {
  file: string;
  matched: number;
  total: number;
  note?: string;
}

// ---- The mentor agent --------------------------------------------------------------------------

export interface ToolContext {
  gh: GitHubClient;
  repo: string;
  branch: string;
  /** Filled by read_file so the answer can be checked against what was really read. */
  reads?: ReadLog;
}

export interface MentorOptions {
  gemini: Gemini;
  ctx: ToolContext;
  issue: Issue;
  comments: { user: string; body: string }[];
  onStep?: (line: string) => void;
  /** Checked before every model call so a closed browser tab stops spending quota. */
  isCancelled?: () => boolean;
}

// ---- The pipeline ------------------------------------------------------------------------------

export interface RankOptions {
  gh: GitHubClient;
  gemini?: Gemini;
  language: string;
  level: Level;
  /** Rank issues of just these repositories instead of searching for repositories first. */
  repos?: Repository[];
  /** Max candidate issues to check on this page. */
  limit: number;
  page?: number;
  /** Drop issues that already have an open PR (default true). */
  hideTaken?: boolean;
  now: number;
  /** Ratings recorded for --demo; used instead of calling Gemini. */
  recordedRatings?: Record<string, DifficultyResult>;
  log?: (message: string) => void;
}

export interface RankResult {
  rows: Row[];
  ratings: Record<string, DifficultyResult>;
  /** Candidates dropped because an open PR already covers them. */
  hiddenTaken: number;
  hasMore: boolean;
}

export interface ExplainOptions {
  gh: GitHubClient;
  gemini?: Gemini;
  repo: Repository;
  issue: Issue;
  /** Recorded answer used by --demo instead of calling Gemini. */
  recordedAnswer?: string;
  onStep?: (line: string) => void;
  isCancelled?: () => boolean;
}
