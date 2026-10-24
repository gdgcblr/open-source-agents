import type { ConsoleEvidenceEntry, NetworkEvidenceEntry, RunResult } from "../types/test-plan.js";

export interface FailureEvidence {
  testId: string;
  testName: string;
  status: string;
  error?: string;
  reproductionSteps: string[];
  consoleErrors: ConsoleEvidenceEntry[];
  networkFailures: NetworkEvidenceEntry[];
  screenshotPaths: string[];
  tracePath?: string;
}

/**
 * Extracts sanitized, reproducible evidence for the failing/blocked test(s) in a run.
 * Passing tests are excluded - this is specifically "why did it fail" evidence.
 */
export function extractFailureEvidence(result: RunResult, testId?: string): FailureEvidence[] {
  const tests = testId ? result.tests.filter((t) => t.id === testId) : result.tests;

  return tests
    .filter((t) => t.status === "FAIL" || t.status === "BLOCKED")
    .map((t) => ({
      testId: t.id,
      testName: t.name,
      status: t.status,
      error: t.error,
      reproductionSteps: t.steps.map(
        (s) => `${s.action}${s.selector ? ` "${s.selector}"` : ""} -> ${s.status}${s.message ? `: ${s.message}` : ""}`,
      ),
      consoleErrors: t.consoleErrors,
      networkFailures: t.networkFailures,
      screenshotPaths: t.screenshotPaths,
      tracePath: t.tracePath,
    }));
}
