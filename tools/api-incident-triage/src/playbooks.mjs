/**
 * Local incident playbooks + risk scores.
 * Scores are heuristic (0–100), not a formal risk model.
 */

/** @typedef {{ score: number, blastRadius: string, ownerHint: string, playbook: string[] }} Playbook */

/** @type {Record<string, Playbook>} */
export const PLAYBOOKS = {
  "database-schema": {
    score: 88,
    blastRadius: "Reads/writes against missing relations fail; user-facing 5xx likely until migrations align.",
    ownerHint: "Backend / data",
    playbook: [
      "Confirm environment and database name (dev vs staging vs prod).",
      "Diff expected schema vs live (migrations, search_path, identifier casing).",
      "Block related deploys until the relation exists or the query is corrected.",
      "Re-run a single synthetic request and confirm the 42P01 signal is gone.",
    ],
  },
  "database-auth": {
    score: 90,
    blastRadius: "All DB-backed requests can fail; cascading API outages are common.",
    ownerHint: "Backend / platform secrets",
    playbook: [
      "Verify DB role password and secret source for this environment.",
      "Check host-based auth rules (pg_hba / cloud allowlists).",
      "Rotate leaked or stale credentials; restart apps picking up new secrets.",
      "Probe with a one-off authenticated connection from the same network path.",
    ],
  },
  "database-constraint": {
    score: 62,
    blastRadius: "Specific writes fail; duplicates/retries may create noisy client errors.",
    ownerHint: "Backend / product",
    playbook: [
      "Identify table + unique constraint from the DB error.",
      "Decide reject vs upsert vs client-side dedupe.",
      "Check retry storms that re-insert the same key.",
      "Add a regression test for the conflict path.",
    ],
  },
  "connection-refused": {
    score: 86,
    blastRadius: "Dependency unreachable; features behind that service are down.",
    ownerHint: "Platform / backend",
    playbook: [
      "Verify host:port and that the process is listening.",
      "Check container/service name DNS and network policies.",
      "Confirm the dependency started before the caller (compose order/healthchecks).",
      "Retest connectivity from the same host/network namespace as the app.",
    ],
  },
  "dns-not-found": {
    score: 84,
    blastRadius: "All calls to that hostname fail until DNS/config is fixed.",
    ownerHint: "Platform / networking",
    playbook: [
      "Validate hostname spelling and environment-specific service DNS.",
      "Check resolver, /etc/hosts, and mesh/ingress aliases.",
      "Confirm the service is registered/deployed in this cluster/network.",
      "Retry after DNS TTL; avoid hardcoding IPs as a permanent fix.",
    ],
  },
  "tls-ssl": {
    score: 80,
    blastRadius: "Encrypted links fail; browsers/clients may block the entire API path.",
    ownerHint: "Platform / security",
    playbook: [
      "Confirm TLS is expected on this port and certs are valid/not expired.",
      "Inspect proxy/LB termination differences across environments.",
      "Fix trust chain; do not disable verification in production.",
      "Retest with openssl/s_client or an equivalent from the app host.",
    ],
  },
  timeout: {
    score: 74,
    blastRadius: "Slow or hung calls; retries can amplify load and timeouts.",
    ownerHint: "Backend / dependency owners",
    playbook: [
      "Measure caller vs dependency latency around the failure window.",
      "Inspect pools, locks, and hot queries before raising timeouts.",
      "Add bounded backoff; stop unbounded retry storms.",
      "Capture one correlated request ID across services.",
    ],
  },
  "resource-exhaustion": {
    score: 92,
    blastRadius: "Process or pool collapse can take down the whole instance.",
    ownerHint: "Backend / SRE",
    playbook: [
      "Check memory graphs, connection counts, and recent traffic spikes.",
      "Look for connection leaks and unbounded concurrency.",
      "Scale or shed load only after identifying the pressure source.",
      "Add alerts on pool utilization and heap usage.",
    ],
  },
  cors: {
    score: 48,
    blastRadius: "Browser clients blocked; server-to-server callers may still work.",
    ownerHint: "Frontend / API gateway",
    playbook: [
      "Confirm allowed origins/methods/headers for this environment.",
      "Reproduce with curl to separate CORS UI errors from backend faults.",
      "Align credentialed requests with ACAO/ACAC settings.",
      "Ship a minimal failing browser repro in the ticket.",
    ],
  },
  "http-401": {
    score: 55,
    blastRadius: "Unauthenticated callers rejected; may look like an outage to clients.",
    ownerHint: "Auth / backend",
    playbook: [
      "Check token presence/expiry without logging secret values.",
      "Confirm clock skew and identity issuer config.",
      "Verify the route actually requires auth as intended.",
    ],
  },
  "http-403": {
    score: 58,
    blastRadius: "Authorized identity lacks permission for this action/resource.",
    ownerHint: "AuthZ / product",
    playbook: [
      "Differentiate missing auth (401) from denied permission (403).",
      "Inspect role/policy mappings for the caller.",
      "Confirm environment-specific permission seeds.",
    ],
  },
  "http-404": {
    score: 40,
    blastRadius: "Single resource/route missing; often localized impact.",
    ownerHint: "API / frontend",
    playbook: [
      "Verify path, method, base URL, and deployed version.",
      "Check soft-deletes and environment data differences.",
    ],
  },
  "http-429": {
    score: 66,
    blastRadius: "Throttled clients; bursts can starve legitimate traffic.",
    ownerHint: "API gateway / backend",
    playbook: [
      "Inspect quota, burst, and Retry-After behavior.",
      "Apply bounded exponential backoff on clients.",
      "Check whether a single noisy tenant is exhausting the budget.",
    ],
  },
  "http-500": {
    score: 70,
    blastRadius: "Unhandled server errors; often a symptom of a deeper signal.",
    ownerHint: "Backend",
    playbook: [
      "Prefer more specific secondary signals (DB/network) when present.",
      "Pull exception + request ID from server logs.",
      "Reproduce with synthetic input after redacting secrets.",
    ],
  },
  "http-502": {
    score: 78,
    blastRadius: "Gateway cannot get a valid upstream response.",
    ownerHint: "Platform / upstream service",
    playbook: [
      "Check upstream health and proxy error logs.",
      "Validate upstream address, TLS, and idle timeouts.",
    ],
  },
  "http-503": {
    score: 76,
    blastRadius: "Service unavailable — deploy, capacity, or dependency issue.",
    ownerHint: "SRE / backend",
    playbook: [
      "Check deploy/rollout and health probes.",
      "Inspect capacity limits and dependency outages.",
    ],
  },
  unknown: {
    score: 25,
    blastRadius: "Unclear; avoid broad mitigations until a signal is found.",
    ownerHint: "On-call engineer",
    playbook: [
      "Gather surrounding logs and request IDs.",
      "Reproduce safely with synthetic data.",
      "Add a focused StackSentry rule if the pattern repeats.",
    ],
  },
  "insufficient-input": {
    score: 5,
    blastRadius: "None — no incident content provided.",
    ownerHint: "Reporter",
    playbook: [
      "Provide a small sanitized log excerpt with timestamps/request IDs.",
    ],
  },
};

/**
 * @param {string} category
 * @returns {Playbook & { category: string }}
 */
export function getPlaybook(category) {
  const base = PLAYBOOKS[category] ?? PLAYBOOKS.unknown;
  return { category, ...base };
}

/**
 * Combine primary playbook score with secondary signals (small bump, capped).
 * @param {string} primaryCategory
 * @param {{ category: string }[]} [secondary]
 */
export function scoreIncident(primaryCategory, secondary = []) {
  const primary = getPlaybook(primaryCategory);
  let score = primary.score;
  for (const s of secondary) {
    const extra = getPlaybook(s.category).score;
    score += Math.round(extra * 0.05);
  }
  return Math.min(100, score);
}
