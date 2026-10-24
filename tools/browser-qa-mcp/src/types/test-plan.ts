export type TestStatus = "PASS" | "FAIL" | "BLOCKED";

export interface StepResult {
  action: string;
  selector?: string;
  status: "ok" | "failed" | "blocked";
  message?: string;
  durationMs: number;
}

export interface ConsoleEvidenceEntry {
  type: string;
  text: string;
  timestamp: string;
}

export interface NetworkEvidenceEntry {
  url: string;
  method: string;
  status?: number;
  failureText?: string;
  timestamp: string;
}

export interface TestResult {
  id: string;
  name: string;
  status: TestStatus;
  steps: StepResult[];
  error?: string;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  screenshotPaths: string[];
  consoleErrors: ConsoleEvidenceEntry[];
  networkFailures: NetworkEvidenceEntry[];
  tracePath?: string;
}

export interface RunResult {
  runId: string;
  planName: string;
  baseUrl: string;
  startedAt: string;
  finishedAt: string;
  status: TestStatus;
  tests: TestResult[];
}
