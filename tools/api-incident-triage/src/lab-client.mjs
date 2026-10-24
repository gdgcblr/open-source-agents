/**
 * Client helpers for the StackSentry Failure Lab (localhost only).
 */
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { localTriage, redactSecrets } from "./core.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const LAB_SERVER = join(ROOT, "lab", "server.mjs");

export const LAB_ROUTES = [
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

export function labBaseUrl() {
  const port = Number(process.env.STACKSENTRY_LAB_PORT || 3857);
  return `http://127.0.0.1:${port}`;
}

export async function labStatus() {
  const base = labBaseUrl();
  try {
    const res = await fetch(`${base}/health`);
    if (!res.ok) {
      return { ok: false, base, error: `HTTP ${res.status}` };
    }
    const body = await res.json();
    return { ok: true, base, ...body };
  } catch (err) {
    return {
      ok: false,
      base,
      error: String(err?.message || err),
      hint: "Start with npm run lab, or call lab_start",
    };
  }
}

export async function labScenarios() {
  const status = await labStatus();
  if (!status.ok) return { ...status, scenarios: LAB_ROUTES };
  try {
    const res = await fetch(`${status.base}/scenarios`);
    const body = await res.json();
    return { ok: true, base: status.base, scenarios: body.scenarios || LAB_ROUTES, logFile: body.logFile };
  } catch (err) {
    return { ok: false, base: status.base, scenarios: LAB_ROUTES, error: String(err?.message || err) };
  }
}

/**
 * @param {string} route e.g. /boom/schema or schema
 */
export async function labBoom(route) {
  const status = await labStatus();
  if (!status.ok) {
    throw new Error(`Failure Lab is not running at ${status.base}. ${status.hint || status.error}`);
  }

  let path = route.startsWith("/") ? route : `/boom/${route}`;
  if (!path.startsWith("/boom/")) path = `/boom/${path.replace(/^\//, "")}`;

  const res = await fetch(`${status.base}${path}`);
  const body = await res.json();
  const text = [body.error, body.sqlstate, body.statusCode, JSON.stringify(body)].filter(Boolean).join("\n");
  const result = localTriage(redactSecrets(text));

  return {
    route: path,
    httpStatus: res.status,
    labResponse: body,
    result,
    summary_for_human: [
      `Lab ${path} → HTTP ${res.status}`,
      `StackSentry primary: ${result.category} (${result.riskScore}/100)`,
      result.title,
    ],
    suggested_tool_next: ["get_playbook", "start_incident", "make_incident_report"],
  };
}

/**
 * Spawn Failure Lab if not already up. Returns status after short wait.
 */
export async function labStart() {
  const existing = await labStatus();
  if (existing.ok) {
    return { started: false, alreadyRunning: true, ...existing };
  }

  const child = spawn(process.execPath, [LAB_SERVER], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: { ...process.env },
  });
  child.unref();

  const base = labBaseUrl();
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const st = await labStatus();
    if (st.ok) return { started: true, alreadyRunning: false, pid: child.pid, ...st };
    await new Promise((r) => setTimeout(r, 150));
  }

  return {
    started: true,
    alreadyRunning: false,
    ok: false,
    base,
    pid: child.pid,
    error: "Spawned lab process but health check did not succeed in time",
    hint: "Check port conflicts or run npm run lab in a terminal",
  };
}
