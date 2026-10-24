import test from "node:test";
import assert from "node:assert/strict";
import { compareTriages, localTriage, redactSecrets } from "../src/core.mjs";
import { getPlaybook, scoreIncident } from "../src/playbooks.mjs";
import { formatMarkdownReport } from "../src/report.mjs";

test("redacts bearer and basic authorization credentials", () => {
  const input = "Authorization: Bearer bearer-secret-123\nauthorization: Basic basic-secret-456";
  const output = redactSecrets(input);
  assert.doesNotMatch(output, /bearer-secret-123|basic-secret-456/);
  assert.equal((output.match(/\[REDACTED\]/g) ?? []).length, 2);
});

test("redacts common key/value secrets case-insensitively", () => {
  const input =
    "API_KEY=api-secret-123 password: 'pw-secret-456' client_secret=client-secret-789 access_token=access-secret-000";
  const output = redactSecrets(input);
  for (const secret of ["api-secret-123", "pw-secret-456", "client-secret-789", "access-secret-000"]) {
    assert.equal(output.includes(secret), false, `secret should be redacted: ${secret}`);
  }
});

test("redacts Postgres URLs that contain credentials", () => {
  const input = "DATABASE_URL=postgresql://service-user:db-password@db.example.test:5432/app";
  const output = redactSecrets(input);
  assert.equal(output.includes("db-password"), false);
  assert.equal(output.includes("service-user"), false);
  assert.match(output, /postgresql:\/\/\[REDACTED\]/);
});

test("identifies a missing PostgreSQL relation before generic HTTP 500", () => {
  const result = localTriage('POST /api/users 500: error: relation "users" does not exist; code 42P01');
  assert.equal(result.category, "database-schema");
  assert.equal(result.confidence, "high");
  assert.ok(result.nextSteps.length >= 2);
  assert.ok(result.secondary.some((s) => s.category === "http-500"));
  assert.ok(result.evidenceSnippets.length >= 1);
  assert.match(result.summary, /database-schema/i);
});

test("identifies a PostgreSQL unique constraint violation", () => {
  const result = localTriage("ERROR: duplicate key value violates unique constraint; SQLSTATE 23505");
  assert.equal(result.category, "database-constraint");
  assert.equal(result.confidence, "high");
});

test("identifies connection refused", () => {
  const result = localTriage("connect ECONNREFUSED 127.0.0.1:5432");
  assert.equal(result.category, "connection-refused");
  assert.equal(result.confidence, "high");
});

test("identifies a timeout with graded confidence", () => {
  assert.equal(localTriage("upstream ETIMEDOUT after 10000ms").confidence, "high");
  assert.equal(localTriage("operation timed out waiting for upstream").confidence, "medium");
  assert.equal(localTriage("config timeout value is 30").confidence, "low");
});

test("identifies supported HTTP status codes", () => {
  assert.equal(localTriage("statusCode: 401 Unauthorized").category, "http-401");
  assert.equal(localTriage("HTTP 403 Forbidden").category, "http-403");
  assert.equal(localTriage("status: 404 Not Found").category, "http-404");
  assert.equal(localTriage("Request failed with statusCode: 429").category, "http-429");
  assert.equal(localTriage("statusCode=500 Internal Server Error").category, "http-500");
  assert.equal(localTriage("HTTP 502 Bad Gateway").category, "http-502");
  assert.equal(localTriage("HTTP 503 Service Unavailable").category, "http-503");
});

test("identifies new Tier A rule families", () => {
  assert.equal(localTriage("getaddrinfo ENOTFOUND db.internal").category, "dns-not-found");
  assert.equal(
    localTriage("FATAL: password authentication failed for user \"app\"; SQLSTATE 28P01").category,
    "database-auth",
  );
  assert.equal(localTriage("SSL handshake failed: certificate verify failed").category, "tls-ssl");
  assert.equal(
    localTriage("Access to fetch blocked by CORS policy: No 'Access-Control-Allow-Origin'").category,
    "cors",
  );
  assert.equal(localTriage("FATAL: remaining connection slots are reserved").category, "resource-exhaustion");
});

test("falls back safely for an unknown error", () => {
  const result = localTriage("some custom failure with no recognized signature");
  assert.equal(result.category, "unknown");
  assert.match(result.title, /not enough evidence/i);
  assert.equal(result.signalCount, 1);
});

test("handles empty input without throwing", () => {
  assert.equal(localTriage("   ").category, "insufficient-input");
});

test("rejects non-string core inputs clearly", () => {
  assert.throws(() => redactSecrets(null), /expects a string/);
  assert.throws(() => localTriage(undefined), /expects a string/);
});

test("multi-signal payload exposes ranked signals and severity", () => {
  const result = localTriage('status=500\nrelation "orders" does not exist\nSQLSTATE: 42P01');
  assert.equal(result.severity, "high");
  assert.ok(result.signals.length >= 2);
  assert.equal(result.signals[0].category, "database-schema");
  assert.ok(result.evidenceSnippets.length >= 1);
});

test("compareTriages detects same vs changed primary incidents", () => {
  const schema = localTriage('relation "users" does not exist SQLSTATE 42P01');
  const again = localTriage('relation "users" does not exist SQLSTATE 42P01');
  const refused = localTriage("connect ECONNREFUSED 127.0.0.1:5432");

  const same = compareTriages(schema, again);
  assert.equal(same.outcome, "same-incident");
  assert.equal(same.samePrimary, true);

  const changed = compareTriages(schema, refused);
  assert.equal(changed.outcome, "primary-changed");
  assert.equal(changed.before.category, "database-schema");
  assert.equal(changed.after.category, "connection-refused");
  assert.match(changed.narrative, /Primary changed/i);
});

test("compareTriages rejects invalid inputs", () => {
  assert.throws(() => compareTriages(null, localTriage("x")), /expects two triage results/);
});

test("triage includes risk score and playbook", () => {
  const result = localTriage('relation "users" does not exist SQLSTATE 42P01');
  assert.equal(typeof result.riskScore, "number");
  assert.ok(result.riskScore >= 80);
  assert.ok(Array.isArray(result.playbook) && result.playbook.length >= 2);
  assert.match(result.blastRadius, /relation|schema|5xx|fail/i);
  assert.ok(result.ownerHint);
});

test("playbook score bumps slightly with secondary signals", () => {
  const base = scoreIncident("database-schema", []);
  const bumped = scoreIncident("database-schema", [{ category: "http-500" }]);
  assert.ok(bumped >= base);
  assert.ok(bumped <= 100);
  assert.equal(getPlaybook("database-schema").score, 88);
});

test("markdown report includes score and playbook", () => {
  const result = localTriage("connect ECONNREFUSED 127.0.0.1:5432");
  const md = formatMarkdownReport(result, { source: "test" });
  assert.match(md, /Risk score/);
  assert.match(md, /Playbook/);
  assert.match(md, /connection-refused/);
});
