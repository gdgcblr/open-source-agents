// Core type definitions for repo-contribution-auditor

export type Severity = "high" | "medium" | "low" | "info";
export type Label = "verified" | "heuristic";

/**
 * A single finding from a deterministic check.
 * All file-derived strings are stored as-is here; redaction/escaping is the
 * responsibility of the output layer.
 */
export interface Finding {
  id: string;
  severity: Severity;
  label: Label;
  /** Check rule identifier, e.g. "readme-sections" */
  rule: string;
  /** Human-readable description */
  description: string;
  /** Relative path within the target root (empty string = project level) */
  file: string;
  /** 1-based line number; 0 means N/A */
  line: number;
  /** Redacted evidence snippet (never raw secret content) */
  evidence: string;
}

/**
 * AI explanation attached to an existing finding after model validation.
 * Max 400 chars. Unknown ids are discarded.
 */
export interface AiAnnotation {
  findingId: string;
  /** Plain text, max 400 chars */
  text: string;
}

export interface AuditResult {
  targetDir: string;
  timestamp: string;
  truncated: boolean;
  truncationReason?: string;
  findings: Finding[];
  annotations: AiAnnotation[];
}

/** Schema for model output validation */
export interface ModelOutput {
  annotations: Array<{
    findingId: string;
    text: string;
  }>;
}

export interface AuditLimits {
  maxFiles: number;
  maxFileSizeBytes: number;
  maxTotalBytes: number;
  maxDepth: number;
}

export const DEFAULT_LIMITS: AuditLimits = {
  maxFiles: 2000,
  maxFileSizeBytes: 512 * 1024,    // 512 KB
  maxTotalBytes: 20 * 1024 * 1024, // 20 MB
  maxDepth: 12,
};

export interface CliOptions {
  targetDir: string;
  explain: boolean;
  confirmSend: boolean;
  outputFormat: "json" | "markdown" | "both";
  /** git base ref for scope check; defaults to "origin/main" */
  baseRef: string;
}
