import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compareTriages, localTriage, redactSecrets } from "./core.mjs";
import { formatMarkdownReport } from "./report.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const EXAMPLES_DIR = join(__dirname, "..", "examples");

const BANNER = `╔══════════════════════════════════════╗
║           StackSentry                ║
║   Local API incident triage (offline)║
╚══════════════════════════════════════╝`;

const USAGE = `StackSentry — local API incident triage

Usage:
  node src/index.mjs <path-to-log-file>
  node src/index.mjs --json <path-to-log-file>
  node src/index.mjs --report reports/incident.md <path-to-log-file>
  node src/index.mjs --demo
  node src/index.mjs compare <before.log> <after.log>
  cat <path-to-log-file> | node src/index.mjs

Options:
  --json, -j              Print structured JSON
  --verbose, -v           Include full signal list and extra detail
  --quiet, -q             One-line incident card only
  --report [path]         Write a markdown incident report (default: reports/incident-report.md)
  --demo                  Guided walkthrough on bundled examples
  --help, -h              Show this help

Lab (separate process):
  npm run lab             Start the intentional failure lab on :3857
  npm run lab:boom        Hit boom routes, append lab/lab.log, triage + report

The tool runs locally and makes no network requests. Secret redaction is best-effort.`;

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

function triageText(raw) {
  const sanitized = redactSecrets(raw);
  return { sanitized, result: localTriage(sanitized) };
}

/**
 * @param {ReturnType<typeof localTriage>} result
 * @param {{ verbose?: boolean, quiet?: boolean, showBanner?: boolean }} [opts]
 */
function formatReport(result, opts = {}) {
  const { verbose = false, quiet = false, showBanner = true } = opts;

  if (quiet) {
    return `${result.severity.toUpperCase()} | score ${result.riskScore}/100 | ${result.category} | ${result.title}`;
  }

  const lines = [];
  if (showBanner) lines.push(BANNER, "");

  lines.push(
    "Incident card",
    "─────────────",
    `  ${result.summary}`,
    "",
    `Risk score:  ${result.riskScore}/100`,
    `Severity:    ${result.severity}`,
    `Primary:     ${result.category}`,
    `Owner hint:  ${result.ownerHint}`,
    `Confidence:  ${result.confidence} (heuristic — verify)`,
    `Signals:     ${result.signalCount}`,
    "",
    `Likely cause: ${result.title}`,
    `Evidence:     ${result.evidence}`,
    "",
    "Blast radius:",
    `  ${result.blastRadius}`,
  );

  if (result.secondary?.length) {
    lines.push("", "Also detected:");
    for (const s of result.secondary) {
      lines.push(`  • ${s.category} (${s.confidence} confidence, ${s.severity} severity)`);
    }
  }

  if (result.evidenceSnippets?.length) {
    lines.push("", "Evidence snippets (sanitized):");
    for (const snippet of result.evidenceSnippets) {
      lines.push(`  | ${snippet}`);
    }
  }

  lines.push("", "Playbook:");
  for (const [index, step] of (result.playbook ?? []).entries()) {
    lines.push(`  ${index + 1}. ${step}`);
  }

  lines.push("", "Suggested checks:");
  for (const [index, step] of result.nextSteps.entries()) {
    lines.push(`  ${index + 1}. ${step}`);
  }

  if (verbose && result.signals?.length) {
    lines.push("", "All signals (verbose):");
    for (const [i, signal] of result.signals.entries()) {
      lines.push(
        `  [${i + 1}] ${signal.category} — ${signal.confidence}/${signal.severity}`,
        `      ${signal.title}`,
        `      ${signal.evidence}`,
      );
      for (const step of signal.nextSteps ?? []) {
        lines.push(`        - ${step}`);
      }
    }
  }

  lines.push(
    "",
    "Privacy: redaction is local and best-effort.",
    "Note: diagnosis is heuristic, not a proven root cause.",
  );

  return lines.join("\n");
}

/**
 * @param {ReturnType<typeof compareTriages>} comparison
 * @param {{ quiet?: boolean, showBanner?: boolean }} [opts]
 */
function formatCompare(comparison, opts = {}) {
  const { quiet = false, showBanner = true } = opts;
  if (quiet) {
    return `${comparison.outcome} | ${comparison.before.category} → ${comparison.after.category} | severity ${comparison.severityDelta}`;
  }

  const lines = [];
  if (showBanner) lines.push(BANNER, "");
  lines.push(
    "Compare — before vs after",
    "─────────────────────────",
    `Outcome:   ${comparison.outcome}`,
    `Severity:  ${comparison.severityDelta}`,
    "",
    "Before:",
    `  ${comparison.before.summary}`,
    "",
    "After:",
    `  ${comparison.after.summary}`,
    "",
    `Primary:   ${comparison.before.category} → ${comparison.after.category}`,
  );

  if (comparison.removedSignals.length) {
    lines.push(`Cleared:   ${comparison.removedSignals.join(", ")}`);
  }
  if (comparison.addedSignals.length) {
    lines.push(`New:       ${comparison.addedSignals.join(", ")}`);
  }

  lines.push("", "Narrative:", `  ${comparison.narrative}`, "", "Privacy: comparison uses locally redacted triage only.");
  return lines.join("\n");
}

function parseArgs(argv) {
  const flags = new Set();
  const positionals = [];
  /** @type {string | null} */
  let reportPath = null;
  let wantsReport = false;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") flags.add("help");
    else if (arg === "--json" || arg === "-j") flags.add("json");
    else if (arg === "--verbose" || arg === "-v") flags.add("verbose");
    else if (arg === "--quiet" || arg === "-q") flags.add("quiet");
    else if (arg === "--demo") flags.add("demo");
    else if (arg === "--compare") flags.add("compare");
    else if (arg === "--report") {
      wantsReport = true;
      flags.add("report");
      const next = argv[i + 1];
      if (next && !next.startsWith("-") && next !== "compare") {
        reportPath = next;
        i += 1;
      } else {
        reportPath = join("reports", "incident-report.md");
      }
    } else if (arg.startsWith("-")) flags.add(`unknown:${arg}`);
    else positionals.push(arg);
  }

  if (positionals[0] === "compare") {
    flags.add("compare");
    positionals.shift();
  }

  return { flags, positionals, reportPath, wantsReport };
}

async function maybeWriteReport(result, reportPath, source) {
  if (!reportPath) return;
  const md = formatMarkdownReport(result, { source });
  await mkdir(dirname(reportPath), { recursive: true });
  await writeFile(reportPath, md, "utf8");
  console.error(`Wrote markdown report: ${reportPath}`);
}

async function runDemo(flags, reportPath) {
  const schemaPath = join(EXAMPLES_DIR, "sample-error.log");
  const refusedPath = join(EXAMPLES_DIR, "connection-refused.log");
  const schemaRaw = await readFile(schemaPath, "utf8");
  const refusedRaw = await readFile(refusedPath, "utf8");
  const schema = triageText(schemaRaw).result;
  const refused = triageText(refusedRaw).result;
  const comparison = compareTriages(schema, refused);

  if (flags.has("json")) {
    console.log(
      JSON.stringify(
        {
          mode: "demo",
          steps: [
            { name: "schema-failure", file: "examples/sample-error.log", result: schema },
            { name: "connection-refused", file: "examples/connection-refused.log", result: refused },
            { name: "compare", result: comparison },
          ],
        },
        null,
        2,
      ),
    );
    return;
  }

  const quiet = flags.has("quiet");
  const verbose = flags.has("verbose") && !quiet;

  console.log(BANNER);
  console.log(`
Demo walkthrough
────────────────
StackSentry stays on your machine: redact → multi-signal triage → playbook/score → report.
No API key. No upload.

Step 1 — Schema / missing relation (examples/sample-error.log)
`);
  console.log(formatReport(schema, { quiet, verbose, showBanner: false }));
  console.log(`
Step 2 — Dependency down (examples/connection-refused.log)
`);
  console.log(formatReport(refused, { quiet, verbose, showBanner: false }));
  console.log(`
Step 3 — Compare the two (different primary incidents)
`);
  console.log(formatCompare(comparison, { quiet, showBanner: false }));
  console.log(`
Takeaway
────────
Day-to-day: triage a log. Mentors: npm run demo. Live breakables: npm run lab + npm run lab:boom.
`);

  if (reportPath) {
    await maybeWriteReport(schema, reportPath, "examples/sample-error.log (demo step 1)");
  }
}

async function main() {
  const { flags, positionals, reportPath, wantsReport } = parseArgs(process.argv.slice(2));

  if (flags.has("help")) {
    console.log(USAGE);
    return;
  }

  const unknown = [...flags].find((f) => f.startsWith("unknown:"));
  if (unknown) {
    console.error(`Unknown option: ${unknown.slice("unknown:".length)}\n\n${USAGE}`);
    process.exitCode = 2;
    return;
  }

  if (flags.has("verbose") && flags.has("quiet")) {
    console.error("Use either --verbose or --quiet, not both.\n\n" + USAGE);
    process.exitCode = 2;
    return;
  }

  if (flags.has("demo")) {
    if (positionals.length > 0) {
      console.error(`--demo does not take file arguments.\n\n${USAGE}`);
      process.exitCode = 2;
      return;
    }
    await runDemo(flags, wantsReport ? reportPath : null);
    return;
  }

  const quiet = flags.has("quiet");
  const verbose = flags.has("verbose");

  if (flags.has("compare")) {
    if (positionals.length !== 2) {
      console.error(`compare requires exactly two log files.\n\n${USAGE}`);
      process.exitCode = 2;
      return;
    }
    let beforeRaw;
    let afterRaw;
    try {
      beforeRaw = await readFile(positionals[0], "utf8");
      afterRaw = await readFile(positionals[1], "utf8");
    } catch (error) {
      const message =
        error && typeof error === "object" && "code" in error && error.code === "ENOENT"
          ? "One of the specified log files was not found."
          : "Could not read the supplied input.";
      console.error(message);
      process.exitCode = 1;
      return;
    }
    const before = triageText(beforeRaw).result;
    const after = triageText(afterRaw).result;
    const comparison = compareTriages(before, after);
    if (flags.has("json")) console.log(JSON.stringify(comparison, null, 2));
    else console.log(formatCompare(comparison, { quiet }));
    return;
  }

  if (positionals.length > 1) {
    console.error(`Expected at most one log-file path (or use: compare <a> <b>).\n\n${USAGE}`);
    process.exitCode = 2;
    return;
  }

  let input;
  let source = "stdin";
  try {
    if (positionals.length === 1) {
      source = positionals[0];
      input = await readFile(positionals[0], "utf8");
    } else if (!process.stdin.isTTY) {
      input = await readStdin();
    } else {
      console.error(`Provide a log file, pipe stdin, try --demo, or npm run lab:boom.\n\n${USAGE}`);
      process.exitCode = 2;
      return;
    }
  } catch (error) {
    const message =
      error && typeof error === "object" && "code" in error && error.code === "ENOENT"
        ? "The specified log file was not found."
        : "Could not read the supplied input.";
    console.error(message);
    process.exitCode = 1;
    return;
  }

  const { sanitized, result } = triageText(input);

  if (flags.has("json")) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(formatReport(result, { verbose, quiet }));
  }

  if (wantsReport) {
    await maybeWriteReport(result, reportPath, source);
  }

  if (!sanitized.trim()) process.exitCode = 1;
}

main().catch(() => {
  console.error("Unexpected error while processing the input.");
  process.exitCode = 1;
});
