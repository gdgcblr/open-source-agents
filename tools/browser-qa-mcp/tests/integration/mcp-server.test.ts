import { createRequire } from "node:module";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { createServer } from "../../src/mcp/server.js";

const require = createRequire(import.meta.url);

const PORT = 4567;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const ARTIFACTS_DIR = path.resolve(import.meta.dirname, "../../artifacts-mcp-test");

process.env.QA_ARTIFACTS_DIR = ARTIFACTS_DIR;
// Sandboxed CI images ship Chromium here; elsewhere fall back to the one `playwright install` downloaded.
if (!process.env.PLAYWRIGHT_CHROMIUM_PATH && existsSync("/opt/pw-browsers/chromium")) {
  process.env.PLAYWRIGHT_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
}

let demoServer: ReturnType<typeof import("node:http").createServer>;
let client: Client;

function toolResultJson(result: { content: Array<{ type: string; text?: string }> }): unknown {
  const text = result.content.find((c) => c.type === "text")?.text;
  return text ? JSON.parse(text) : undefined;
}

beforeAll(async () => {
  process.env.PORT = String(PORT);
  // Reuse the exact same demo app the manual/README workflow runs against.
  delete require.cache[require.resolve("../../fixtures/demo-app/server.js")];
  demoServer = require("../../fixtures/demo-app/server.js");

  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const server = createServer();
  await server.connect(serverTransport);

  client = new Client({ name: "test-client", version: "0.0.0" });
  await client.connect(clientTransport);
}, 30_000);

afterAll(async () => {
  await new Promise<void>((resolve) => demoServer.close(() => resolve()));
  rmSync(ARTIFACTS_DIR, { recursive: true, force: true });
});

describe("MCP server (real client/server round trip over InMemoryTransport)", () => {
  it("lists all five tools", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((t) => t.name).sort();
    expect(names).toEqual(
      ["get_failure_evidence", "get_run_report", "inspect_page", "plan_qa_test", "run_qa_test"].sort(),
    );
  });

  it("rejects run_qa_test with an invalid test plan", async () => {
    const result = await client.callTool({ name: "run_qa_test", arguments: { testPlan: { not: "a plan" } } });
    expect(result.isError).toBe(true);
    const body = toolResultJson(result as never) as { error: string };
    expect(body.error).toBe("invalid_test_plan");
  });

  it("runs a real test plan end-to-end and reports PASS/FAIL per test", async () => {
    const testPlan = {
      version: 1,
      name: "MCP integration plan",
      baseUrl: BASE_URL,
      tests: [
        {
          id: "signup-success",
          name: "Valid signup succeeds",
          steps: [
            { action: "navigate", url: "/signup" },
            { action: "fill", selector: "input[name='name']", value: "Ada" },
            { action: "fill", selector: "input[name='email']", value: "ada@example.com" },
            { action: "fill", selector: "input[name='password']", value: "secret123" },
            { action: "click", selector: "button[type='submit']" },
            { action: "assert_visible", selector: "#signup-success" },
          ],
        },
        {
          id: "signup-invalid-email",
          name: "Invalid email is rejected (expected to fail - real app bug)",
          steps: [
            { action: "navigate", url: "/signup" },
            { action: "fill", selector: "input[name='name']", value: "Ada" },
            { action: "fill", selector: "input[name='email']", value: "invalid-email" },
            { action: "fill", selector: "input[name='password']", value: "secret123" },
            { action: "click", selector: "button[type='submit']" },
            { action: "assert_visible", selector: "[role='alert']" },
          ],
        },
      ],
    };

    const runResult = await client.callTool({
      name: "run_qa_test",
      arguments: { testPlan, allowLocalDev: true },
    });
    expect(runResult.isError).toBeFalsy();
    const body = toolResultJson(runResult as never) as {
      runId: string;
      status: string;
      tests: Array<{ id: string; status: string }>;
    };

    expect(body.status).toBe("FAIL");
    expect(body.tests.find((t) => t.id === "signup-success")?.status).toBe("PASS");
    expect(body.tests.find((t) => t.id === "signup-invalid-email")?.status).toBe("FAIL");

    const reportResult = await client.callTool({ name: "get_run_report", arguments: { runId: body.runId } });
    expect(reportResult.isError).toBeFalsy();
    const report = toolResultJson(reportResult as never) as { runId: string };
    expect(report.runId).toBe(body.runId);

    const evidenceResult = await client.callTool({
      name: "get_failure_evidence",
      arguments: { runId: body.runId },
    });
    expect(evidenceResult.isError).toBeFalsy();
    const evidence = toolResultJson(evidenceResult as never) as Array<{ testId: string; screenshotPaths: string[] }>;
    expect(evidence).toHaveLength(1);
    expect(evidence[0].testId).toBe("signup-invalid-email");
    expect(evidence[0].screenshotPaths.length).toBeGreaterThan(0);
  }, 30_000);

  it("reports an unknown runId as an error rather than throwing", async () => {
    const result = await client.callTool({ name: "get_run_report", arguments: { runId: "does-not-exist" } });
    expect(result.isError).toBe(true);
  });

  it("inspect_page returns bounded, read-only page info", async () => {
    const result = await client.callTool({
      name: "inspect_page",
      arguments: { url: `${BASE_URL}/signup`, allowLocalDev: true },
    });
    expect(result.isError).toBeFalsy();
    const body = toolResultJson(result as never) as { title: string; interactiveElements: unknown[] };
    expect(body.title).toBe("Sign up");
    expect(body.interactiveElements.length).toBeGreaterThan(0);
  }, 15_000);

  it("blocks inspect_page against a loopback target without allowLocalDev", async () => {
    const result = await client.callTool({ name: "inspect_page", arguments: { url: `${BASE_URL}/signup` } });
    expect(result.isError).toBe(true);
  });

  it("plan_qa_test reports a clear configuration error with no API key set", async () => {
    const originalKey = process.env.ANTHROPIC_API_KEY;
    delete process.env.ANTHROPIC_API_KEY;
    try {
      const result = await client.callTool({
        name: "plan_qa_test",
        arguments: { request: "test the signup flow", baseUrl: BASE_URL },
      });
      expect(result.isError).toBe(true);
      const body = toolResultJson(result as never) as { error: string };
      expect(body.error).toMatch(/not configured/);
    } finally {
      if (originalKey) process.env.ANTHROPIC_API_KEY = originalKey;
    }
  });
});
