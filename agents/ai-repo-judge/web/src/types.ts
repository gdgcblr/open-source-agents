// Mirrors judge/models.py and the index written by judge/pipeline.py.

export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type Status = "pass" | "warn" | "fail" | "skip";
export type Verdict = "ready" | "needs_changes" | "blocked";
export type DimensionKey = "compliance" | "security" | "quality" | "functionality" | "ai_native" | "docs" | "innovation";

export interface Finding {
  dimension: DimensionKey;
  severity: Severity;
  title: string;
  detail: string;
  file: string | null;
  line: number | null;
  snippet: string | null;
  fix: string | null;
  commit: string | null;
  source: "static" | "llm";
  gate: boolean;
}

export interface Check {
  id: string;
  dimension: DimensionKey;
  label: string;
  status: Status;
  weight: number;
  score: number | null;
  detail: string;
  fix: string | null;
}

export interface DimensionResult {
  key: DimensionKey;
  label: string;
  weight: number;
  purpose: string;
  score: number | null;
  static_score: number | null;
  llm_score: number | null;
  llm_share: number;
  llm_rationale: string | null;
  checks: Check[];
  findings: Finding[];
}

export interface Claim {
  feature: string;
  status: "implemented" | "partial" | "missing" | "unverified";
  evidence: string;
}

export interface Submission {
  id: string;
  number: number | null;
  title: string;
  url: string | null;
  author: string | null;
  author_avatar: string | null;
  state: string;
  created_at: string | null;
  updated_at: string | null;
  head_sha: string;
  category: "agents" | "tools" | "unknown";
  slug: string;
  project_path: string;
  extra_projects: string[];
  files: { path: string; lines: number; language: string; findings: number }[];
  loc: number;
  languages: Record<string, number>;
  frameworks: string[];
  providers: string[];
  ai_level: number;
  ai_level_label: string;
  ai_level_evidence: string[];
  claims: Claim[];
  summary: string | null;
  strengths: string[];
  top_fixes: string[];
  dimensions: DimensionResult[];
  overall: number;
  verdict: Verdict;
  gates: string[];
  confidence: number;
  manipulation_suspected: boolean;
  llm: { used: boolean; provider: string | null; model: string | null; tokens: number; error: string | null };
  similar: { id: string; slug: string; title: string; score: number; kind: "idea" | "code" }[];
  history: { sha: string; judged_at: string; overall: number; verdict: Verdict }[];
  judged_at: string;
  judge_version: string;
}

export interface SubmissionSummary {
  id: string;
  number: number | null;
  title: string;
  url: string | null;
  author: string | null;
  author_avatar: string | null;
  state: string;
  category: string;
  slug: string;
  overall: number;
  verdict: Verdict;
  confidence: number;
  scores: Partial<Record<DimensionKey, number | null>>;
  frameworks: string[];
  providers: string[];
  languages: string[];
  ai_level: number;
  ai_level_label: string;
  severity_counts: Record<Severity, number>;
  top_fix: string | null;
  head_sha: string;
  judged_at: string;
  updated_at: string | null;
  llm_used: boolean;
}

export interface RubricEntry {
  key: DimensionKey;
  label: string;
  weight: number;
  llm_share: number;
  purpose: string;
}

export interface Tally {
  name: string;
  count: number;
}

export interface Insights {
  count: number;
  by_verdict: Partial<Record<Verdict, number>>;
  by_category: Record<string, number>;
  by_state: Record<string, number>;
  avg_overall: number;
  median_overall: number;
  dimension_avg: Partial<Record<DimensionKey, number | null>>;
  dimension_median: Partial<Record<DimensionKey, number | null>>;
  histogram: { bucket: string; count: number }[];
  providers: Tally[];
  frameworks: Tally[];
  languages: Tally[];
  ai_levels: { level: number; count: number }[];
  common_issues: { check_id: string; dimension: DimensionKey; label: string; fail: number; warn: number; share: number }[];
  clusters: { members: string[]; titles: string[] }[];
  secrets_found: number;
  manipulation_attempts: number;
  llm_tokens: number;
}

export interface ResultsIndex {
  generated_at: string;
  repo: string | null;
  judge_version: string;
  prompt_version: string;
  rubric: RubricEntry[];
  thresholds: { ready: number; manipulation_penalty: number };
  submissions: SubmissionSummary[];
  insights: Insights;
  errors: { id: string; title: string | null; url: string | null; error: string }[];
}
