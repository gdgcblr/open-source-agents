import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { safeValidateTestPlan } from "../planner/schema.js";
import { runTestPlan } from "../runner/test-runner.js";
import { RunStore, isValidRunId } from "../runner/run-store.js";
import { retentionFromEnv } from "../evidence/artifact-retention.js";
import { TargetPolicy } from "../security/target-policy.js";
import { inspectPage } from "../runner/inspect-page.js";
import { extractFailureEvidence } from "../evidence/failure-evidence.js";
import { diagnoseFailure } from "../diagnosis/failure-analyzer.js";
import { isPlannerConfigured, planTestFromDescription } from "../planner/llm-planner.js";

const ARTIFACTS_BASE_DIR = process.env.QA_ARTIFACTS_DIR || "./artifacts";

function jsonContent(value: unknown, isError = false) {
  return { isError, content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

/**
 * Builds the MCP server. All four tools below call the exact same
 * runner/assertion/security services the CLI uses (src/runner,
 * src/assertions, src/security) - there is no separate "MCP version" of
 * the browser logic.
 */
export function createServer(): McpServer {
  const server = new McpServer({ name: "browser-qa-mcp", version: "0.1.0" });
  const runStore = new RunStore(ARTIFACTS_BASE_DIR);

  server.registerTool(
    "run_qa_test",
    {
      title: "Run a browser QA test plan",
      description:
        "Executes a structured, schema-validated browser QA test plan with Playwright and returns verified PASS/FAIL/BLOCKED results per test, with evidence references (screenshots, console errors, failed network requests, trace files). A successful click or navigation is never reported as a pass - only the plan's explicit assert_* steps determine test status. Loopback/private-network targets are blocked unless allowLocalDev is set.",
      inputSchema: {
        testPlan: z
          .record(z.string(), z.unknown())
          .describe("A test plan object: { version: 1, name, baseUrl, tests: [{ id, name, steps: [...] }] }. See examples/signup-flow.json or use plan_qa_test to generate one."),
        allowLocalDev: z
          .boolean()
          .optional()
          .describe("Set true to permit navigating to loopback/private-network targets (e.g. a local dev server). Defaults to false."),
        allowedOrigins: z
          .array(z.string())
          .optional()
          .describe("Optional allow-list of exact origins (scheme+host+port) navigation is restricted to."),
      },
    },
    async ({ testPlan, allowLocalDev, allowedOrigins }) => {
      const validation = safeValidateTestPlan(testPlan);
      if (!validation.success) {
        return jsonContent({ error: "invalid_test_plan", issues: validation.error.format() }, true);
      }
      const result = await runTestPlan(validation.data, { allowLocalDev, allowedOrigins, artifactsBaseDir: ARTIFACTS_BASE_DIR, retention: retentionFromEnv() });
      runStore.save(result);
      return jsonContent(result);
    },
  );

  server.registerTool(
    "inspect_page",
    {
      title: "Inspect a page's interactive elements",
      description:
        "Loads a page read-only and returns its title, URL, and a bounded list of interactive elements (tag, role, accessible name, a selector hint) to help write or debug a test plan's selectors. Does not submit forms, click anything, or run arbitrary script.",
      inputSchema: {
        url: z.string().describe("Absolute URL to load."),
        allowLocalDev: z.boolean().optional().describe("Set true to permit inspecting a loopback/private-network target."),
      },
    },
    async ({ url, allowLocalDev }) => {
      const targetPolicy = new TargetPolicy({ allowLocalDev });
      try {
        const inspection = await inspectPage(url, targetPolicy);
        return jsonContent(inspection);
      } catch (err) {
        return jsonContent({ error: (err as Error).message }, true);
      }
    },
  );

  server.registerTool(
    "get_run_report",
    {
      title: "Get a run's full report",
      description:
        "Retrieves the full structured report for a previous run_qa_test run by its runId, including every test's status, step-by-step results, and artifact (screenshot/trace) paths.",
      inputSchema: {
        runId: z.string().describe("The runId returned by run_qa_test."),
      },
    },
    async ({ runId }) => {
      if (!isValidRunId(runId)) {
        return jsonContent({ error: `Invalid runId "${runId}": expected a UUID returned by run_qa_test` }, true);
      }
      const result = runStore.get(runId);
      if (!result) {
        return jsonContent({ error: `No run found for runId "${runId}"` }, true);
      }
      return jsonContent(result);
    },
  );

  server.registerTool(
    "get_failure_evidence",
    {
      title: "Get evidence for a run's failures",
      description:
        "Returns sanitized console errors, failed network requests, screenshot/trace paths, and reproduction steps for the failing or blocked test(s) in a run. Optionally attaches a model-generated causal hypothesis (explicitly labeled as such, never as a verified finding) when diagnose is true and ANTHROPIC_API_KEY is configured.",
      inputSchema: {
        runId: z.string().describe("The runId returned by run_qa_test."),
        testId: z.string().optional().describe("Limit evidence to a single test ID. Omit to get evidence for every failing/blocked test in the run."),
        diagnose: z
          .boolean()
          .optional()
          .describe("Set true to also attach an LLM-generated hypothesis (requires ANTHROPIC_API_KEY). Defaults to false."),
      },
    },
    async ({ runId, testId, diagnose }) => {
      if (!isValidRunId(runId)) {
        return jsonContent({ error: `Invalid runId "${runId}": expected a UUID returned by run_qa_test` }, true);
      }
      const result = runStore.get(runId);
      if (!result) {
        return jsonContent({ error: `No run found for runId "${runId}"` }, true);
      }

      const evidence = extractFailureEvidence(result, testId);
      if (evidence.length === 0) {
        return jsonContent({ message: "No failing or blocked tests found for the given runId/testId." });
      }

      if (!diagnose) {
        return jsonContent(evidence);
      }

      const withDiagnosis = await Promise.all(
        evidence.map(async (e) => ({ ...e, diagnosis: await diagnoseFailure(e) })),
      );
      return jsonContent(withDiagnosis);
    },
  );

  server.registerTool(
    "plan_qa_test",
    {
      title: "Draft a test plan from a natural-language request",
      description:
        "Converts a natural-language testing request into a validated, schema-conformant test plan using an LLM. Requires ANTHROPIC_API_KEY. The generated plan is validated exactly as a hand-written one would be and can be rejected (e.g. if it uses an unsupported action or the model tries to point it at a different origin). This tool never executes the plan or marks anything passed/failed - pass its output to run_qa_test for verified results.",
      inputSchema: {
        request: z
          .string()
          .describe("Natural-language description of what to test, e.g. 'Test the signup flow: required fields, invalid email, and a successful signup.'"),
        baseUrl: z.string().describe("The application origin to test, e.g. http://127.0.0.1:4000"),
      },
    },
    async ({ request, baseUrl }) => {
      if (!isPlannerConfigured()) {
        return jsonContent(
          { error: "The AI planner is not configured. Set ANTHROPIC_API_KEY, or write a test plan JSON by hand (see examples/signup-flow.json)." },
          true,
        );
      }
      try {
        const plan = await planTestFromDescription(request, baseUrl);
        return jsonContent(plan);
      } catch (err) {
        return jsonContent({ error: (err as Error).message }, true);
      }
    },
  );

  return server;
}
