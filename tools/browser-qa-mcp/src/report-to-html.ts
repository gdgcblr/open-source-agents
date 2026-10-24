#!/usr/bin/env node
import { writeFileSync } from "node:fs";
import { readReport } from "./reports/json-reporter.js";
import { renderHtmlReport } from "./reports/html-reporter.js";

/**
 * Converts an already-saved report.json (e.g. one you pulled via the MCP
 * server's get_run_report tool and saved to disk) into a standalone HTML
 * file - a separate entry point from `run:plan --html` because this one
 * never launches a browser or needs a test plan.
 */
function main(): void {
  const [reportPath, outPath] = process.argv.slice(2);
  if (!reportPath) {
    console.error("Usage: report:html <path-to-report.json> [out.html]");
    process.exitCode = 1;
    return;
  }

  const result = readReport(reportPath);
  const html = renderHtmlReport(result);
  const resolvedOutPath = outPath ?? reportPath.replace(/\.json$/i, ".html");
  writeFileSync(resolvedOutPath, html);
  console.log(`HTML report written to ${resolvedOutPath}`);
}

main();
