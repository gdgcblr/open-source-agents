/**
 * StackSentry Failure Lab — intentional breakable HTTP API (Node built-ins only).
 * Synthetic errors only. Writes to lab/lab.log for offline triage demos.
 */
import { createServer } from "node:http";
import { appendFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOG_PATH = join(__dirname, "lab.log");
const PORT = Number(process.env.STACKSENTRY_LAB_PORT || 3857);

const SCENARIOS = {
  "/boom/schema": {
    status: 500,
    body: {
      error: 'DatabaseError: relation "users" does not exist',
      sqlstate: "42P01",
    },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/schema status=500\n` +
      `DatabaseError: relation "users" does not exist\n` +
      `SQLSTATE: 42P01\n` +
      `Authorization: Bearer lab-demo-token-schema\n` +
      `DATABASE_URL=postgresql://lab-user:lab-password@localhost:5432/lab_app\n`,
  },
  "/boom/refused": {
    status: 503,
    body: { error: "connect ECONNREFUSED 127.0.0.1:5432" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/refused\n` +
      `Error: connect ECONNREFUSED 127.0.0.1:5432\n` +
      `Authorization: Bearer lab-demo-token-refused\n` +
      `API_KEY=lab-api-key-should-be-redacted\n`,
  },
  "/boom/duplicate": {
    status: 409,
    body: { error: "duplicate key value violates unique constraint", sqlstate: "23505" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=POST path=/boom/duplicate status=409\n` +
      `ERROR: duplicate key value violates unique constraint "users_email_key"; SQLSTATE 23505\n`,
  },
  "/boom/auth-db": {
    status: 500,
    body: { error: "password authentication failed", sqlstate: "28P01" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/auth-db\n` +
      `FATAL: password authentication failed for user "lab_app"; SQLSTATE 28P01\n`,
  },
  "/boom/timeout": {
    status: 504,
    body: { error: "upstream ETIMEDOUT after 10000ms" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/timeout status=504\n` +
      `upstream ETIMEDOUT after 10000ms\n`,
  },
  "/boom/dns": {
    status: 502,
    body: { error: "getaddrinfo ENOTFOUND db.internal.lab" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/dns\n` +
      `Error: getaddrinfo ENOTFOUND db.internal.lab\n`,
  },
  "/boom/tls": {
    status: 502,
    body: { error: "SSL handshake failed: certificate verify failed" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/tls\n` +
      `Error: SSL handshake failed: certificate verify failed\n`,
  },
  "/boom/rate-limit": {
    status: 429,
    body: { error: "Too Many Requests", statusCode: 429 },
    log: (id) =>
      `${ts()} WARN request_id=${id} method=GET path=/boom/rate-limit\n` +
      `Request failed with statusCode: 429 Too Many Requests\n`,
  },
  "/boom/cors": {
    status: 403,
    body: { error: "CORS blocked" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/cors\n` +
      `Access to fetch at 'http://localhost:${PORT}/api' blocked by CORS policy: No 'Access-Control-Allow-Origin'\n`,
  },
  "/boom/pool": {
    status: 500,
    body: { error: "remaining connection slots are reserved" },
    log: (id) =>
      `${ts()} ERROR request_id=${id} method=GET path=/boom/pool\n` +
      `FATAL: remaining connection slots are reserved\n`,
  },
};

function ts() {
  return new Date().toISOString();
}

function requestId() {
  return `lab_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

async function appendLog(chunk) {
  await mkdir(__dirname, { recursive: true });
  await appendFile(LOG_PATH, chunk.endsWith("\n") ? chunk : `${chunk}\n`, "utf8");
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;

  if (path === "/health") {
    sendJson(res, 200, { ok: true, service: "stacksentry-failure-lab", port: PORT });
    return;
  }

  if (path === "/" || path === "/scenarios") {
    sendJson(res, 200, {
      service: "stacksentry-failure-lab",
      logFile: LOG_PATH,
      scenarios: Object.keys(SCENARIOS),
      hint: "GET a /boom/* route, then: node src/index.mjs lab/lab.log",
    });
    return;
  }

  const scenario = SCENARIOS[path];
  if (!scenario) {
    sendJson(res, 404, { error: "Unknown route", try: Object.keys(SCENARIOS) });
    return;
  }

  const id = requestId();
  try {
    await appendLog(scenario.log(id));
  } catch {
    // Still return the synthetic failure even if disk write fails.
  }

  sendJson(res, scenario.status, { request_id: id, ...scenario.body, logged: true });
});

server.on("error", (err) => {
  if (err && err.code === "EADDRINUSE") {
    console.error(`Port ${PORT} is already in use.`);
    console.error(`Free it, or use another port:`);
    console.error(`  PowerShell: Get-NetTCPConnection -LocalPort ${PORT} | Select OwningProcess`);
    console.error(`  Then: Stop-Process -Id <PID> -Force`);
    console.error(`  Or:   $env:STACKSENTRY_LAB_PORT=3858; npm run lab`);
    process.exitCode = 1;
    return;
  }
  console.error(err);
  process.exitCode = 1;
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`StackSentry Failure Lab listening on http://127.0.0.1:${PORT}`);
  console.log(`Log file: ${LOG_PATH}`);
  console.log(`Scenarios: ${Object.keys(SCENARIOS).join(", ")}`);
  console.log("Try: curl http://127.0.0.1:" + PORT + "/boom/schema");
});
