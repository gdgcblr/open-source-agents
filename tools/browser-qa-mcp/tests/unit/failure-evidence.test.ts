import { describe, expect, it } from "vitest";
import { extractFailureEvidence } from "../../src/evidence/failure-evidence.js";
import type { RunResult } from "../../src/types/test-plan.js";

function makeRun(overrides: Partial<RunResult> = {}): RunResult {
  return {
    runId: "run-1",
    planName: "demo",
    baseUrl: "http://127.0.0.1:4000",
    startedAt: "2026-01-01T00:00:00.000Z",
    finishedAt: "2026-01-01T00:00:01.000Z",
    status: "FAIL",
    tests: [
      {
        id: "t-pass",
        name: "Passing test",
        status: "PASS",
        steps: [{ action: "navigate", status: "ok", durationMs: 10 }],
        startedAt: "2026-01-01T00:00:00.000Z",
        finishedAt: "2026-01-01T00:00:00.500Z",
        durationMs: 500,
        screenshotPaths: [],
        consoleErrors: [],
        networkFailures: [],
      },
      {
        id: "t-fail",
        name: "Failing test",
        status: "FAIL",
        steps: [
          { action: "navigate", status: "ok", durationMs: 10 },
          { action: "assert_visible", selector: "[role='alert']", status: "failed", message: "not visible", durationMs: 5000 },
        ],
        error: "not visible",
        startedAt: "2026-01-01T00:00:00.500Z",
        finishedAt: "2026-01-01T00:00:01.000Z",
        durationMs: 500,
        screenshotPaths: ["artifacts/run-1/t-fail-failure-1.png"],
        consoleErrors: [{ type: "error", text: "TypeError: x is undefined", timestamp: "2026-01-01T00:00:00.800Z" }],
        networkFailures: [{ url: "http://127.0.0.1:4000/api", method: "POST", status: 500, timestamp: "2026-01-01T00:00:00.900Z" }],
        tracePath: "artifacts/run-1/t-fail-trace.zip",
      },
    ],
    ...overrides,
  };
}

describe("extractFailureEvidence", () => {
  it("excludes passing tests", () => {
    const evidence = extractFailureEvidence(makeRun());
    expect(evidence).toHaveLength(1);
    expect(evidence[0].testId).toBe("t-fail");
  });

  it("includes console errors, network failures, screenshots, and trace path", () => {
    const [evidence] = extractFailureEvidence(makeRun());
    expect(evidence.consoleErrors).toHaveLength(1);
    expect(evidence.networkFailures).toHaveLength(1);
    expect(evidence.screenshotPaths).toHaveLength(1);
    expect(evidence.tracePath).toBe("artifacts/run-1/t-fail-trace.zip");
  });

  it("builds human-readable reproduction steps from the step history", () => {
    const [evidence] = extractFailureEvidence(makeRun());
    expect(evidence.reproductionSteps[0]).toContain("navigate");
    expect(evidence.reproductionSteps[1]).toContain("assert_visible");
    expect(evidence.reproductionSteps[1]).toContain("not visible");
  });

  it("filters to a single test when testId is given", () => {
    const evidence = extractFailureEvidence(makeRun(), "t-fail");
    expect(evidence).toHaveLength(1);
  });

  it("returns an empty array when the named test does not exist or is not failing", () => {
    expect(extractFailureEvidence(makeRun(), "t-pass")).toHaveLength(0);
    expect(extractFailureEvidence(makeRun(), "nonexistent")).toHaveLength(0);
  });
});
