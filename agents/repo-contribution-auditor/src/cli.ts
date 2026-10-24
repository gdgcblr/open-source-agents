#!/usr/bin/env node
/**
 * CLI entry point for repo-contribution-auditor.
 *
 * Usage:
 *   npx tsx src/cli.ts <target-dir> [options]
 *   node dist/cli.js <target-dir> [options]
 *
 * Options:
 *   --explain          Enable AI explanations (requires GEMINI_API_KEY in env)
 *   --confirm-send     Required with --explain; confirms you consent to sending
 *                      redacted finding JSON to the Gemini API
 *   --format <mode>    Output format: json | markdown | both (default: both)
 *   --base-ref <ref>   Git base ref for scope check (default: origin/main)
 *   --help             Show this help message
 *
 * Exit codes:
 *   0  All checks pass (or only medium/low/info findings)
 *   1  One or more HIGH severity findings
 *   2  Usage error
 */

// Load .env from the CWD if present (never from target dir)
import { config as loadEnv } from "dotenv";
loadEnv();

import { audit } from "./auditor.js";
import { formatJson, formatMarkdown, determineExitCode } from "./formatter.js";
import { createProvider } from "./aiProvider.js";
import type { CliOptions } from "./types.js";

const HELP = `
Usage: audit <target-dir> [options]

Arguments:
  <target-dir>   Path to the project folder to audit

Options:
  --explain          Enable AI explanations (requires GEMINI_API_KEY env var)
  --confirm-send     Required when using --explain; confirms consent to send
                     redacted finding JSON to the Gemini API
  --format <mode>    Output format: json | markdown | both (default: both)
  --base-ref <ref>   Git base ref for scope check (default: origin/main)
  --help             Show this help message

Environment variables:
  GEMINI_API_KEY     Gemini API key (only used with --explain --confirm-send)

Exit codes:
  0  No HIGH severity findings
  1  At least one HIGH severity finding
  2  Usage / argument error
`.trim();

function parseArgs(argv: string[]): CliOptions & { help: boolean } {
  const args = argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    return {
      targetDir: "",
      explain: false,
      confirmSend: false,
      outputFormat: "both",
      baseRef: "origin/main",
      help: true,
    };
  }

  const positionals = args.filter((a) => !a.startsWith("-"));
  if (positionals.length === 0) {
    console.error("Error: <target-dir> argument is required");
    process.exit(2);
  }

  const targetDir = positionals[0] as string;
  const explain = args.includes("--explain");
  const confirmSend = args.includes("--confirm-send");

  const fmtIdx = args.indexOf("--format");
  let outputFormat: "json" | "markdown" | "both" = "both";
  if (fmtIdx !== -1) {
    const v = args[fmtIdx + 1];
    if (v === "json" || v === "markdown" || v === "both") {
      outputFormat = v;
    } else {
      console.error(`Error: --format must be one of: json, markdown, both`);
      process.exit(2);
    }
  }

  const baseIdx = args.indexOf("--base-ref");
  const baseRef = baseIdx !== -1 ? (args[baseIdx + 1] ?? "origin/main") : "origin/main";

  return {
    targetDir,
    explain,
    confirmSend,
    outputFormat,
    baseRef,
    help: false,
  };
}

async function main(): Promise<void> {
  const opts = parseArgs(process.argv);

  if (opts.help) {
    console.log(HELP);
    process.exit(0);
  }

  if (opts.explain && !opts.confirmSend) {
    console.error(
      "Error: --explain requires --confirm-send to acknowledge that redacted finding " +
        "JSON will be sent to the Gemini API."
    );
    process.exit(2);
  }

  // Print what will be sent before any network call
  if (opts.explain && opts.confirmSend) {
    console.error(
      "[info] --explain is active. Only REDACTED finding JSON (id, severity, rule, " +
        "description, file, line, evidence) will be sent to Gemini. No file contents are transmitted."
    );
  }

  const apiKey = process.env["GEMINI_API_KEY"];
  const provider = opts.explain ? createProvider(apiKey) : null;

  let result;
  try {
    result = await audit(opts, provider);
  } catch (err) {
    console.error(`Fatal error: ${String(err)}`);
    process.exit(2);
  }

  if (opts.outputFormat === "json" || opts.outputFormat === "both") {
    console.log(formatJson(result));
  }

  if (opts.outputFormat === "markdown" || opts.outputFormat === "both") {
    if (opts.outputFormat === "both") {
      console.log("\n---\n");
    }
    console.log(formatMarkdown(result));
  }

  process.exit(determineExitCode(result.findings));
}

main().catch((err: unknown) => {
  console.error("Unhandled error:", err);
  process.exit(2);
});
