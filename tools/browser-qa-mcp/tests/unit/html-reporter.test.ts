import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { renderHtmlReport } from "../../src/reports/html-reporter.js";
import type { RunResult } from "../../src/types/test-plan.js";

function makeRun(overrides: Partial<RunResult> = {}): RunResult {
  return {
    runId: "run-1",
    planName: "Signup flow",
    baseUrl: "http://127.0.0.1:4000",
    startedAt: "2026-01-01T00:00:00.000Z",
    finishedAt: "2026-01-01T00:00:01.000Z",
    status: "FAIL",
    tests: [
      {
        id: "t-pass",
        name: "Valid signup succeeds",
        status: "PASS",
        steps: [{ action: "navigate", status: "ok", durationMs: 10, message: "Navigated to /signup" }],
        startedAt: "2026-01-01T00:00:00.000Z",
        finishedAt: "2026-01-01T00:00:00.500Z",
        durationMs: 500,
        screenshotPaths: [],
        consoleErrors: [],
        networkFailures: [],
      },
      {
        id: "t-fail",
        name: "Invalid email is rejected",
        status: "FAIL",
        steps: [
          { action: "navigate", status: "ok", durationMs: 10 },
          { action: "assert_visible", selector: "[role='alert']", status: "failed", message: "not visible", durationMs: 5000 },
        ],
        error: "not visible",
        startedAt: "2026-01-01T00:00:00.500Z",
        finishedAt: "2026-01-01T00:00:01.000Z",
        durationMs: 500,
        screenshotPaths: [],
        consoleErrors: [{ type: "error", text: "TypeError: x is undefined", timestamp: "2026-01-01T00:00:00.800Z" }],
        networkFailures: [{ url: "http://127.0.0.1:4000/api", method: "POST", status: 500, timestamp: "2026-01-01T00:00:00.900Z" }],
        tracePath: "artifacts/run-1/t-fail-trace.zip",
      },
    ],
    ...overrides,
  };
}

describe("renderHtmlReport", () => {
  it("renders a self-contained HTML document with the run summary", () => {
    const html = renderHtmlReport(makeRun());
    expect(html).toContain("<!doctype html>");
    expect(html).toContain("Signup flow");
    expect(html).toContain("run-1");
    expect(html).toContain("1 passed");
    expect(html).toContain("1 failed");
    expect(html).toContain("0 blocked");
  });

  it("renders each test's status, steps, and error", () => {
    const html = renderHtmlReport(makeRun());
    expect(html).toContain("Valid signup succeeds");
    expect(html).toContain("Invalid email is rejected");
    expect(html).toContain("not visible");
    expect(html).toContain("assert_visible");
  });

  it("renders console errors and network failures", () => {
    const html = renderHtmlReport(makeRun());
    expect(html).toContain("TypeError: x is undefined");
    expect(html).toContain("http://127.0.0.1:4000/api");
    expect(html).toContain("500");
  });

  it("renders a local, offline command to view the trace rather than pointing only at an external site", () => {
    const html = renderHtmlReport(makeRun());
    expect(html).toContain("npx playwright show-trace");
    expect(html).toContain("artifacts/run-1/t-fail-trace.zip");
  });

  it("notes a missing screenshot file instead of crashing", () => {
    const run = makeRun();
    run.tests[1].screenshotPaths = ["artifacts/run-1/does-not-exist.png"];
    const html = renderHtmlReport(run);
    expect(html).toContain("Screenshot not found on disk");
    expect(html).toContain("does-not-exist.png");
  });

  it("embeds an existing screenshot as a base64 data URI", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "html-reporter-"));
    const screenshotPath = path.join(dir, "shot.png");
    // Minimal 1x1 PNG signature bytes - content doesn't matter, just needs to exist and be readable.
    writeFileSync(screenshotPath, Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));

    const run = makeRun();
    run.tests[1].screenshotPaths = [screenshotPath];
    const html = renderHtmlReport(run);

    expect(html).toContain("data:image/png;base64,");
    expect(html).not.toContain("Screenshot not found");

    rmSync(dir, { recursive: true, force: true });
  });

  describe("HTML escaping (XSS safety)", () => {
    it("escapes a malicious console error message instead of injecting it as markup", () => {
      const run = makeRun();
      run.tests[1].consoleErrors = [
        { type: "error", text: "<script>alert('pwned')</script>", timestamp: "2026-01-01T00:00:00.800Z" },
      ];
      const html = renderHtmlReport(run);
      expect(html).not.toContain("<script>alert");
      expect(html).toContain("&lt;script&gt;");
    });

    it("escapes a malicious assertion error message", () => {
      const run = makeRun();
      run.tests[1].error = '<img src=x onerror="alert(1)">';
      const html = renderHtmlReport(run);
      expect(html).not.toContain("<img src=x onerror=");
      expect(html).toContain("&lt;img");
    });

    it("escapes a malicious selector from the test plan", () => {
      const run = makeRun();
      run.tests[1].steps[1].selector = "\"></li><script>alert(1)</script>";
      const html = renderHtmlReport(run);
      expect(html).not.toContain("<script>alert(1)</script>");
    });

    it("escapes a malicious network URL", () => {
      const run = makeRun();
      run.tests[1].networkFailures = [
        { url: "http://x/</li><script>alert(1)</script>", method: "GET", timestamp: "2026-01-01T00:00:00.900Z" },
      ];
      const html = renderHtmlReport(run);
      expect(html).not.toContain("<script>alert(1)</script>");
    });

    it("escapes a malicious plan name and base URL", () => {
      const run = makeRun({ planName: "<script>alert('plan')</script>", baseUrl: "http://x/\"><script>alert(2)</script>" });
      const html = renderHtmlReport(run);
      expect(html).not.toContain("<script>alert('plan')</script>");
      expect(html).not.toContain("<script>alert(2)</script>");
    });
  });
});
