#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { safeValidateTestPlan } from "./planner/schema.js";
import { runTestPlan } from "./runner/test-runner.js";
import { renderHtmlReport } from "./reports/html-reporter.js";
import { retentionFromEnv } from "./evidence/artifact-retention.js";

async function main(): Promise<void> {
  const [planPath, ...rest] = process.argv.slice(2);
  if (!planPath) {
    console.error("Usage: run:plan <path-to-test-plan.json> [--allow-local-dev] [--out <report.json>] [--html <report.html>]");
    process.exitCode = 1;
    return;
  }

  const allowLocalDev = rest.includes("--allow-local-dev");
  const outIndex = rest.indexOf("--out");
  const outPath = outIndex >= 0 ? rest[outIndex + 1] : undefined;
  const htmlIndex = rest.indexOf("--html");
  const htmlPath = htmlIndex >= 0 ? rest[htmlIndex + 1] : undefined;

  const raw = JSON.parse(readFileSync(planPath, "utf-8"));
  const validation = safeValidateTestPlan(raw);
  if (!validation.success) {
    console.error("Test plan failed validation:");
    console.error(JSON.stringify(validation.error.format(), null, 2));
    process.exitCode = 1;
    return;
  }

  const result = await runTestPlan(validation.data, {
    allowLocalDev,
    artifactsBaseDir: process.env.QA_ARTIFACTS_DIR || "./artifacts",
    retention: retentionFromEnv(),
  });
  const json = JSON.stringify(result, null, 2);

  if (outPath) {
    writeFileSync(outPath, json);
    console.log(`Report written to ${outPath}`);
  } else {
    console.log(json);
  }

  if (htmlPath) {
    writeFileSync(htmlPath, renderHtmlReport(result));
    console.log(`HTML report written to ${htmlPath}`);
  }

  console.error(`\nRun status: ${result.status} (runId: ${result.runId})`);
  process.exitCode = result.status === "PASS" ? 0 : 1;
}

main().catch((err) => {
  console.error("Fatal error running test plan:", err);
  process.exitCode = 1;
});
