export type Severity = 'error' | 'warning';

export interface Finding {
  severity: Severity;
  message: string;
  fix?: string;
}

export interface CheckResult {
  check: string;
  passed: boolean;
  skipped?: string;
  findings: Finding[];
}

export interface ProjectSource {
  label: string;
  /** Repository-relative project folder, e.g. `agents/my-agent`. */
  projectPath: string;
  /** Files that would be committed, relative to the project folder. */
  files: string[];
  /** PR mode only: every repository-relative path the PR touches. */
  changedFiles?: string[];
  readFile(relPath: string): Promise<string | null>;
}

export function toResult(check: string, findings: Finding[]): CheckResult {
  return {check, passed: !findings.some((f) => f.severity === 'error'), findings};
}
