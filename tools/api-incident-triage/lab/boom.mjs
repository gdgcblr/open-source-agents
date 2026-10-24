/**
 * Hit each lab boom route, show how StackSentry classifies it, then triage the full log.
 * Assumes: npm run lab  (already running)
 */
import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { localTriage, redactSecrets } from "../src/core.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const LOG_PATH = join(__dirname, "lab.log");
const PORT = Number(process.env.STACKSENTRY_LAB_PORT || 3857);
const BASE = `http://127.0.0.1:${PORT}`;

const ROUTES = [
  "/boom/schema",
  "/boom/refused",
  "/boom/duplicate",
  "/boom/auth-db",
  "/boom/timeout",
  "/boom/dns",
  "/boom/tls",
  "/boom/rate-limit",
  "/boom/cors",
  "/boom/pool",
];

async function waitForLab(timeoutMs = 5000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`Lab not reachable at ${BASE}. Start it first with: npm run lab`);
}

function classifyResponse(body) {
  const text = [body.error, body.sqlstate, body.statusCode, JSON.stringify(body)]
    .filter(Boolean)
    .join("\n");
  return localTriage(redactSecrets(text));
}

async function main() {
  await waitForLab();

  // Fresh log so an old schema line does not dominate forever.
  await writeFile(LOG_PATH, "", "utf8");

  console.log(`StackSentry Lab Boom — ${BASE}`);
  console.log("Each route returns a FIXED synthetic error (by design).");
  console.log("Watch the Category column change per route:\n");
  console.log(
    `${"Route".padEnd(22)} ${"HTTP".padStart(4)}  ${"Category".padEnd(22)} Score`,
  );
  console.log(`${"-".repeat(22)} ${"-".repeat(4)}  ${"-".repeat(22)} -----`);

  for (const route of ROUTES) {
    const res = await fetch(`${BASE}${route}`);
    const body = await res.json();
    const triage = classifyResponse(body);
    console.log(
      `${route.padEnd(22)} ${String(res.status).padStart(4)}  ${triage.category.padEnd(22)} ${triage.riskScore}/100`,
    );
  }

  console.log(`\nFull combined log written to: ${LOG_PATH}`);
  console.log(
    "Note: combined triage picks the strongest primary (often database-schema).",
  );
  console.log("For a single failure class, hit one route then triage only that request.\n");

  const reportPath = join(ROOT, "reports", "lab-incident-report.md");
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["src/index.mjs", "--report", reportPath, LOG_PATH],
      { cwd: ROOT, stdio: "inherit" },
    );
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`triage exit ${code}`))));
    child.on("error", reject);
  });

  console.log(`\nTry different JSON yourself:`);
  console.log(`  curl ${BASE}/boom/refused`);
  console.log(`  curl ${BASE}/boom/timeout`);
  console.log(`  curl ${BASE}/boom/rate-limit`);
}

main().catch((err) => {
  console.error(String(err.message || err));
  process.exitCode = 1;
});
