import { randomUUID } from "node:crypto";
import type { ValidatedTestPlan } from "../planner/schema.js";
import type {
  ConsoleEvidenceEntry,
  NetworkEvidenceEntry,
  RunResult,
  StepResult,
  TestResult,
  TestStatus,
} from "../types/test-plan.js";
import { TargetPolicy } from "../security/target-policy.js";
import { ArtifactManager } from "../evidence/artifact-manager.js";
import { ConsoleCollector } from "../evidence/console-collector.js";
import { NetworkCollector } from "../evidence/network-collector.js";
import { writeReport } from "../reports/json-reporter.js";
import { pruneArtifacts, type RetentionPolicy } from "../evidence/artifact-retention.js";
import { BrowserManager, type TestSession } from "./browser-manager.js";
import { ActionBlockedError, executeAction } from "./action-executor.js";
import { AssertionFailedError, executeAssertion, isAssertionAction } from "../assertions/assertion-engine.js";
import { PlaywrightAssertablePage } from "./playwright-page-adapter.js";

export interface RunPlanOptions {
  /** Explicit opt-in required to navigate to loopback/private-network targets. */
  allowLocalDev?: boolean;
  /** Restrict navigation to this exact set of origins, in addition to the base policy. */
  allowedOrigins?: string[];
  /** Directory runs are written under, one subdirectory per runId. Defaults to ./artifacts. */
  artifactsBaseDir?: string;
  /** Old runs to delete after this one is written. Omit to keep everything. */
  retention?: RetentionPolicy;
}

type TestCase = ValidatedTestPlan["tests"][number];

export async function runTestPlan(plan: ValidatedTestPlan, options: RunPlanOptions = {}): Promise<RunResult> {
  const runId = randomUUID();
  const artifactManager = new ArtifactManager(options.artifactsBaseDir ?? "./artifacts", runId);

  const targetPolicy = new TargetPolicy({
    allowLocalDev: options.allowLocalDev,
    allowedOrigins: options.allowedOrigins,
  });

  const startedAt = new Date().toISOString();
  const baseUrlVerdict = targetPolicy.evaluate(plan.baseUrl);

  let result: RunResult;

  if (!baseUrlVerdict.allowed) {
    result = buildBlockedRun(runId, plan, startedAt, baseUrlVerdict.reason);
  } else {
    const browserManager = new BrowserManager();
    let launched = false;
    try {
      await browserManager.launch();
      launched = true;

      const tests: TestResult[] = [];
      for (const test of plan.tests) {
        tests.push(await runSingleTest(test, plan.baseUrl, browserManager, targetPolicy, artifactManager));
      }

      const finishedAt = new Date().toISOString();
      const status: TestStatus = tests.some((t) => t.status === "FAIL")
        ? "FAIL"
        : tests.some((t) => t.status === "BLOCKED")
          ? "BLOCKED"
          : "PASS";

      result = { runId, planName: plan.name, baseUrl: plan.baseUrl, startedAt, finishedAt, status, tests };
    } catch (err) {
      if (launched) throw err; // a failure inside the test loop is a bug, not an environment problem - don't mask it
      result = buildBlockedRun(runId, plan, startedAt, `Failed to launch the browser: ${(err as Error).message}`);
    } finally {
      await browserManager.close();
    }
  }

  writeReport(result, artifactManager.reportPath());
  if (options.retention) {
    pruneArtifacts(options.artifactsBaseDir ?? "./artifacts", options.retention, { keep: [runId] });
  }
  return result;
}

function buildBlockedRun(runId: string, plan: ValidatedTestPlan, startedAt: string, reason: string | undefined): RunResult {
  const finishedAt = new Date().toISOString();
  return {
    runId,
    planName: plan.name,
    baseUrl: plan.baseUrl,
    startedAt,
    finishedAt,
    status: "BLOCKED",
    tests: plan.tests.map((test) => ({
      id: test.id,
      name: test.name,
      status: "BLOCKED" as TestStatus,
      steps: [],
      error: reason,
      startedAt,
      finishedAt,
      durationMs: 0,
      screenshotPaths: [],
      consoleErrors: [],
      networkFailures: [],
    })),
  };
}

async function runSingleTest(
  test: TestCase,
  baseUrl: string,
  browserManager: BrowserManager,
  targetPolicy: TargetPolicy,
  artifactManager: ArtifactManager,
): Promise<TestResult> {
  const startedAt = new Date().toISOString();
  const steps: StepResult[] = [];
  const screenshotPaths: string[] = [];
  let status: TestStatus = "PASS";
  let error: string | undefined;

  let session: TestSession;
  try {
    session = await browserManager.openTestSession(targetPolicy);
  } catch (err) {
    const finishedAt = new Date().toISOString();
    return {
      id: test.id,
      name: test.name,
      status: "BLOCKED",
      steps: [],
      error: `Failed to open an isolated browser context: ${(err as Error).message}`,
      startedAt,
      finishedAt,
      durationMs: 0,
      screenshotPaths: [],
      consoleErrors: [],
      networkFailures: [],
    };
  }

  const assertablePage = new PlaywrightAssertablePage(session.page);
  const consoleCollector = new ConsoleCollector(session.page);
  const networkCollector = new NetworkCollector(session.page);
  await session.context.tracing.start({ screenshots: true, snapshots: true }).catch(() => {});

  let consoleErrors: ConsoleEvidenceEntry[] = [];
  let networkFailures: NetworkEvidenceEntry[] = [];
  let tracePath: string | undefined;

  try {
    for (const step of test.steps) {
      const stepStart = Date.now();
      try {
        throwIfNavigationBlocked(session);
        if (isAssertionAction(step.action)) {
          const message = await executeAssertion(step, assertablePage, baseUrl);
          steps.push({ action: step.action, selector: step.selector, status: "ok", message, durationMs: Date.now() - stepStart });
        } else {
          const outcome = await executeAction(step, {
            page: session.page,
            baseUrl,
            targetPolicy,
            screenshotDir: artifactManager.runDir,
            testId: test.id,
          });
          if (outcome.screenshotPath) screenshotPaths.push(outcome.screenshotPath);
          steps.push({
            action: step.action,
            selector: step.selector,
            status: "ok",
            message: outcome.message,
            durationMs: Date.now() - stepStart,
          });
        }
      } catch (caught) {
        const durationMs = Date.now() - stepStart;
        // A redirect or click into a blocked target shows up as a timeout or net error; report the policy reason instead.
        const blocked = session.networkGuard.takeBlockedNavigation();
        const err = blocked ? new ActionBlockedError(blocked.reason) : caught;
        if (err instanceof AssertionFailedError) {
          steps.push({ action: step.action, selector: step.selector, status: "failed", message: err.message, durationMs });
          status = "FAIL";
          error = err.message;
          await captureFailureScreenshot(session, artifactManager, test.id, screenshotPaths);
        } else if (err instanceof ActionBlockedError) {
          steps.push({ action: step.action, selector: step.selector, status: "blocked", message: err.message, durationMs });
          status = "BLOCKED";
          error = err.message;
        } else {
          // Environmental/infrastructure failure (timeout, crashed page, etc.) -
          // kept distinct from an application assertion failure.
          steps.push({ action: step.action, selector: step.selector, status: "blocked", message: (err as Error).message, durationMs });
          status = "BLOCKED";
          error = (err as Error).message;
        }
        break;
      }
    }
    if (status === "PASS") {
      const blocked = session.networkGuard.takeBlockedNavigation();
      if (blocked) {
        status = "BLOCKED";
        error = blocked.reason;
      }
    }
  } finally {
    consoleErrors = consoleCollector.getEntries();
    networkFailures = networkCollector.getEntries();
    consoleCollector.dispose();
    networkCollector.dispose();

    if (status === "FAIL" || status === "BLOCKED") {
      const candidate = artifactManager.tracePath(test.id);
      try {
        await session.context.tracing.stop({ path: candidate });
        tracePath = candidate;
      } catch {
        // Tracing may not have started successfully; trace capture is best-effort.
      }
    } else {
      await session.context.tracing.stop().catch(() => {});
    }

    await browserManager.closeTestSession(session);
  }

  const finishedAt = new Date().toISOString();
  return {
    id: test.id,
    name: test.name,
    status,
    steps,
    error,
    startedAt,
    finishedAt,
    durationMs: new Date(finishedAt).getTime() - new Date(startedAt).getTime(),
    screenshotPaths,
    consoleErrors,
    networkFailures,
    tracePath,
  };
}

function throwIfNavigationBlocked(session: TestSession): void {
  const blocked = session.networkGuard.takeBlockedNavigation();
  if (blocked) throw new ActionBlockedError(blocked.reason);
}

async function captureFailureScreenshot(
  session: TestSession,
  artifactManager: ArtifactManager,
  testId: string,
  screenshotPaths: string[],
): Promise<void> {
  const path = artifactManager.screenshotPath(testId, "failure");
  try {
    await session.page.screenshot({ path });
    screenshotPaths.push(path);
  } catch {
    // Page may already be closed/crashed - evidence capture is best-effort.
  }
}
