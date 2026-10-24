import { getPlaybook, scoreIncident } from "./playbooks.mjs";

const REDACTED = "[REDACTED]";

/**
 * Redact common credential patterns from text before displaying or sharing it.
 * This is intentionally a best-effort helper, not a complete secret scanner.
 * @param {string} input
 * @returns {string}
 */
export function redactSecrets(input) {
  if (typeof input !== "string") {
    throw new TypeError("redactSecrets(input) expects a string");
  }

  return input
    .replace(/(\bauthorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+/gi, `$1${REDACTED}`)
    .replace(
      /(\b(?:api[_-]?key|password|passwd|secret|access[_-]?token|refresh[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?key)\b\s*[=:]\s*)(["']?)([^\s"'`,;]+)\2/gi,
      `$1${REDACTED}`,
    )
    .replace(/\b(postgres(?:ql)?:\/\/)[^\s"'<>]+/gi, `$1${REDACTED}`);
}

/**
 * @typedef {"high" | "medium" | "low"} Confidence
 * @typedef {"high" | "medium" | "low"} Severity
 *
 * @typedef {object} Signal
 * @property {string} category
 * @property {string} title
 * @property {string} evidence
 * @property {Confidence} confidence
 * @property {Severity} severity
 * @property {string[]} nextSteps
 * @property {number} rank lower = stronger primary candidate
 * @property {string[]} evidenceSnippets
 */

const HTTP_GUIDANCE = {
  "401": [
    "Confirm authentication credentials and token expiry.",
    "Check whether the expected Authorization header is present without logging its value.",
  ],
  "403": [
    "Verify the caller's permissions and role/policy checks.",
    "Distinguish authorization denial from a missing or expired identity.",
  ],
  "404": [
    "Confirm the route, HTTP method, base URL, and deployment version.",
    "Check whether the requested resource exists in the intended environment.",
  ],
  "429": [
    "Inspect rate-limit quotas, request bursts, and retry-after headers.",
    "Use bounded exponential backoff rather than immediate repeated retries.",
  ],
  "500": [
    "Inspect the server-side exception and correlated request ID.",
    "Check adjacent application and database logs before assuming the HTTP status is the root cause.",
  ],
  "502": [
    "Check upstream health and reverse-proxy/gateway logs.",
    "Verify upstream address, TLS, and connection behavior.",
  ],
  "503": [
    "Check service health, deployment status, and capacity limits.",
    "Inspect maintenance state and upstream dependency availability.",
  ],
};

/**
 * Collect up to `limit` non-empty lines that match `lineTest`.
 * @param {string} text
 * @param {(line: string) => boolean} lineTest
 * @param {number} [limit]
 */
function collectSnippets(text, lineTest, limit = 3) {
  const snippets = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || !lineTest(line)) continue;
    snippets.push(line.length > 200 ? `${line.slice(0, 197)}...` : line);
    if (snippets.length >= limit) break;
  }
  return snippets;
}

/**
 * @param {object} partial
 * @returns {Signal}
 */
function signal(partial) {
  return {
    confidence: "medium",
    severity: "medium",
    evidenceSnippets: [],
    nextSteps: [],
    ...partial,
  };
}

/**
 * Detect every matching diagnostic family (multi-signal), then pick a primary.
 * Top-level category/title/evidence/confidence/nextSteps mirror the primary signal
 * for backward-compatible callers.
 * @param {string} input
 */
export function localTriage(input) {
  if (typeof input !== "string") {
    throw new TypeError("localTriage(input) expects a string");
  }

  const text = input.trim();
  if (!text) {
    const empty = signal({
      category: "insufficient-input",
      title: "No log content was provided.",
      evidence: "The input is empty or contains only whitespace.",
      confidence: "low",
      severity: "low",
      rank: 100,
      nextSteps: [
        "Provide a relevant error message or a small sanitized log excerpt.",
        "Include the timestamp, request ID, and adjacent error lines when available.",
      ],
      evidenceSnippets: [],
    });
    return finalize([empty], text);
  }

  /** @type {Signal[]} */
  const found = [];

  // --- Database schema (42P01) ---
  {
    const exact = /\b42P01\b/i.test(text);
    const wording =
      /\b(?:relation|table)\s+["'`]?[^\s"'`]+["'`]?(?:\s+does not exist|\s+not found)\b/i.test(text) ||
      /\brelation\s+.+\s+does not exist\b/i.test(text);
    if (exact || wording) {
      found.push(
        signal({
          category: "database-schema",
          title: "PostgreSQL may be unable to find a referenced table or relation.",
          evidence: exact
            ? "Matched SQLSTATE 42P01 (undefined_table)."
            : "Matched wording associated with an undefined relation/table.",
          confidence: exact ? "high" : "medium",
          severity: "high",
          rank: 10,
          nextSteps: [
            "Confirm the application is connected to the intended database and environment.",
            "Check the relation name, identifier casing, active schema, and search_path.",
            "Verify that the expected migrations ran successfully in this environment.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /42P01|does not exist|relation|table/i.test(line),
          ),
        }),
      );
    }
  }

  // --- Database auth (28P01) ---
  {
    const exact = /\b28P01\b/i.test(text);
    const wording = /password authentication failed|authentication failed for user/i.test(text);
    if (exact || wording) {
      found.push(
        signal({
          category: "database-auth",
          title: "PostgreSQL authentication may have failed for the configured role.",
          evidence: exact
            ? "Matched SQLSTATE 28P01 (invalid_password)."
            : "Matched PostgreSQL password/authentication failure wording.",
          confidence: exact ? "high" : "medium",
          severity: "high",
          rank: 15,
          nextSteps: [
            "Verify DB username/password and that secrets match this environment.",
            "Confirm the role is allowed to connect from this host (pg_hba.conf / cloud rules).",
            "Rotate credentials if a stale secret may have been deployed.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /28P01|authentication failed|password authentication/i.test(line),
          ),
        }),
      );
    }
  }

  // --- Unique constraint (23505) ---
  {
    const exact = /\b23505\b/i.test(text);
    const wording = /duplicate\s+key|unique\s+constraint/i.test(text);
    if (exact || wording) {
      found.push(
        signal({
          category: "database-constraint",
          title: "A database uniqueness constraint may have rejected a write.",
          evidence: exact
            ? "Matched SQLSTATE 23505 (unique_violation)."
            : "Matched duplicate-key/unique-constraint wording.",
          confidence: exact ? "high" : "medium",
          severity: "medium",
          rank: 20,
          nextSteps: [
            "Identify the table and constraint named in the full database error.",
            "Check whether the request was retried or the same record was created concurrently.",
            "Confirm whether the application should reject, upsert, or deduplicate this operation.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /23505|duplicate\s+key|unique\s+constraint/i.test(line),
          ),
        }),
      );
    }
  }

  // --- Connection refused ---
  {
    const exact = /\bECONNREFUSED\b/i.test(text);
    const wording = /connection refused/i.test(text);
    if (exact || wording) {
      found.push(
        signal({
          category: "connection-refused",
          title: "A network connection was actively refused by the target endpoint.",
          evidence: exact
            ? "Matched ECONNREFUSED."
            : "Matched connection-refused wording.",
          confidence: exact ? "high" : "medium",
          severity: "high",
          rank: 30,
          nextSteps: [
            "Verify the host and port configured for the dependency.",
            "Check whether the service is running and listening on the expected interface.",
            "Confirm network rules, container/service names, and environment-specific configuration.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /ECONNREFUSED|connection refused/i.test(line),
          ),
        }),
      );
    }
  }

  // --- DNS not found ---
  {
    const exact = /\bENOTFOUND\b/i.test(text);
    const wording = /getaddrinfo\s+ENOTFOUND|DNS\s+lookup failed|could not resolve host/i.test(text);
    if (exact || wording) {
      found.push(
        signal({
          category: "dns-not-found",
          title: "Hostname resolution may have failed for a dependency.",
          evidence: exact ? "Matched ENOTFOUND." : "Matched DNS / host-resolution failure wording.",
          confidence: exact ? "high" : "medium",
          severity: "high",
          rank: 35,
          nextSteps: [
            "Confirm the hostname spelling and environment-specific service DNS name.",
            "Check local/resolver DNS, /etc/hosts, and container network aliases.",
            "Verify the dependency is deployed and discoverable from this network.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /ENOTFOUND|getaddrinfo|resolve host|DNS/i.test(line),
          ),
        }),
      );
    }
  }

  // --- TLS / SSL ---
  {
    const hit =
      /SSL\s+handshake|TLS\s+handshake|certificate\s+verify\s+failed|UNABLE_TO_VERIFY_LEAF_SIGNATURE|self[- ]signed certificate|ERR_TLS|ssl3_get_record|wrong version number/i.test(
        text,
      );
    if (hit) {
      found.push(
        signal({
          category: "tls-ssl",
          title: "A TLS/SSL handshake or certificate problem may be blocking the connection.",
          evidence: "Matched TLS/SSL handshake or certificate-related wording.",
          confidence: "medium",
          severity: "high",
          rank: 40,
          nextSteps: [
            "Confirm the client expects TLS on this port and that certificates are valid/not expired.",
            "Check whether a proxy or load balancer terminates TLS differently per environment.",
            "Avoid disabling verification in production; fix the trust chain instead.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /SSL|TLS|certificate|ERR_TLS|handshake/i.test(line),
          ),
        }),
      );
    }
  }

  // --- Timeout ---
  {
    const exact = /\bETIMEDOUT\b/i.test(text);
    const strong = /\b(?:request|connection|operation)\s+timed?\s*out\b/i.test(text);
    const vague = !exact && !strong && /\btimeout\b/i.test(text);
    if (exact || strong || vague) {
      found.push(
        signal({
          category: "timeout",
          title: "An operation may be exceeding its time limit.",
          evidence: exact
            ? "Matched ETIMEDOUT."
            : strong
              ? "Matched explicit timed-out wording."
              : "Matched generic timeout wording (higher false-positive risk).",
          confidence: exact ? "high" : strong ? "medium" : "low",
          severity: exact || strong ? "high" : "medium",
          rank: 50,
          nextSteps: [
            "Check the timestamp and duration across the caller and dependency logs.",
            "Inspect dependency latency, connection-pool saturation, and retry behavior.",
            "Avoid increasing timeouts until the source of the delay is understood.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /ETIMEDOUT|timed?\s*out|timeout/i.test(line),
          ),
        }),
      );
    }
  }

  // --- Memory / pool pressure ---
  {
    const hit =
      /\bENOMEM\b|JavaScript heap out of memory|out of memory|connection pool.*(?:exhausted|timeout)|too many connections|remaining connection slots are reserved/i.test(
        text,
      );
    if (hit) {
      found.push(
        signal({
          category: "resource-exhaustion",
          title: "Memory pressure or connection-pool exhaustion may be involved.",
          evidence: "Matched out-of-memory or connection-pool exhaustion wording.",
          confidence: "medium",
          severity: "high",
          rank: 55,
          nextSteps: [
            "Inspect process memory, leak suspects, and recent traffic spikes.",
            "Check DB/app connection pool size, idle clients, and leak of unreleased connections.",
            "Correlate with deploy changes that increased concurrency or payload size.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /ENOMEM|out of memory|connection pool|too many connections|connection slots/i.test(line),
          ),
        }),
      );
    }
  }

  // --- CORS ---
  {
    const hit =
      /Access-Control-Allow-Origin|CORS\s+policy|blocked by CORS|No 'Access-Control-Allow-Origin'/i.test(
        text,
      );
    if (hit) {
      found.push(
        signal({
          category: "cors",
          title: "A browser CORS policy may be blocking the request.",
          evidence: "Matched CORS / Access-Control-Allow-Origin wording.",
          confidence: "medium",
          severity: "medium",
          rank: 60,
          nextSteps: [
            "Confirm allowed origins, methods, and headers on the API for this environment.",
            "Check whether the browser call uses credentials and matching ACAO/ACAC settings.",
            "Reproduce with curl/HTTP client to separate CORS UI errors from backend failures.",
          ],
          evidenceSnippets: collectSnippets(
            text,
            (line) => /CORS|Access-Control-Allow-Origin/i.test(line),
          ),
        }),
      );
    }
  }

  // --- HTTP statuses (can co-exist with more specific signals) ---
  {
    const httpStatus =
      text.match(
        /(?:\bHTTP\s*\/?\s*\d(?:\.\d)?\s+|\bstatus(?:Code)?\s*[=: ]\s*|\bstatus\s+)(401|403|404|429|500|502|503)\b/i,
      )?.[1] ??
      text.match(
        /\b(401|403|404|429|500|502|503)\s+(?:Internal Server Error|Bad Gateway|Service Unavailable|Not Found|Unauthorized|Forbidden|Too Many Requests)\b/i,
      )?.[1] ??
      text.match(/\bHTTP\/\d(?:\.\d)?\s+(401|403|404|429|500|502|503)\b/i)?.[1] ??
      text.match(
        /\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+\s+(401|403|404|429|500|502|503)\b/i,
      )?.[1];

    if (httpStatus) {
      const severity = ["500", "502", "503"].includes(httpStatus)
        ? "high"
        : httpStatus === "429"
          ? "medium"
          : "medium";
      found.push(
        signal({
          category: `http-${httpStatus}`,
          title: `An HTTP ${httpStatus} response was detected; the underlying cause needs verification.`,
          evidence: `Matched an HTTP/status-code signal for ${httpStatus}.`,
          confidence: "medium",
          severity,
          rank: 70 + Number(httpStatus) / 1000,
          nextSteps: HTTP_GUIDANCE[httpStatus],
          evidenceSnippets: collectSnippets(
            text,
            (line) => new RegExp(`\\b${httpStatus}\\b`).test(line),
          ),
        }),
      );
    }
  }

  if (found.length === 0) {
    found.push(
      signal({
        category: "unknown",
        title: "There is not enough evidence to identify a specific failure pattern.",
        evidence: "No currently supported diagnostic signal matched the input.",
        confidence: "low",
        severity: "low",
        rank: 90,
        nextSteps: [
          "Inspect a small amount of surrounding log context and correlate by timestamp/request ID.",
          "Check the relevant service's logs and dependency health.",
          "Reproduce the issue safely with synthetic or sanitized data and add a focused rule if useful.",
        ],
        evidenceSnippets: collectSnippets(text, () => true, 2),
      }),
    );
  }

  return finalize(found, text);
}

/**
 * @param {Signal[]} found
 * @param {string} text
 */
function finalize(found, text) {
  const signals = [...found].sort((a, b) => a.rank - b.rank || severityRank(b.severity) - severityRank(a.severity));
  const primary = signals[0];
  const secondary = signals.slice(1);

  const summary = buildSummary(primary, secondary);
  const evidenceSnippets = uniqueSnippets([
    ...primary.evidenceSnippets,
    ...secondary.flatMap((s) => s.evidenceSnippets),
  ]).slice(0, 3);

  const secondaryView = secondary.map((s) => ({
    category: s.category,
    title: s.title,
    confidence: s.confidence,
    severity: s.severity,
  }));
  const playbook = getPlaybook(primary.category);
  const riskScore = scoreIncident(primary.category, secondaryView);

  return {
    // Primary fields (backward compatible)
    category: primary.category,
    title: primary.title,
    evidence: primary.evidence,
    confidence: primary.confidence,
    nextSteps: primary.nextSteps.slice(0, 3),
    // Tier A enrichments
    severity: primary.severity,
    summary,
    signals: signals.map(({ rank, ...rest }) => {
      void rank;
      return rest;
    }),
    secondary: secondaryView,
    evidenceSnippets,
    signalCount: signals.length,
    // Playbook + score
    riskScore,
    blastRadius: playbook.blastRadius,
    ownerHint: playbook.ownerHint,
    playbook: playbook.playbook,
  };
}

/** @param {Severity} s */
function severityRank(s) {
  return s === "high" ? 3 : s === "medium" ? 2 : 1;
}

/**
 * @param {Signal} primary
 * @param {Signal[]} secondary
 */
function buildSummary(primary, secondary) {
  const also =
    secondary.length > 0
      ? ` Also seen: ${secondary.map((s) => s.category).join(", ")}.`
      : "";
  return `[${primary.severity.toUpperCase()}] ${primary.category}: ${primary.title}${also}`;
}

/** @param {string[]} items */
function uniqueSnippets(items) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    if (seen.has(item)) continue;
    seen.add(item);
    out.push(item);
  }
  return out;
}

/**
 * Compare two triage results (e.g. before/after mitigation logs).
 * Pure helper — no I/O.
 * @param {ReturnType<typeof localTriage>} before
 * @param {ReturnType<typeof localTriage>} after
 */
export function compareTriages(before, after) {
  if (!before || !after || typeof before !== "object" || typeof after !== "object") {
    throw new TypeError("compareTriages(before, after) expects two triage results");
  }

  const beforeCats = new Set((before.signals ?? []).map((s) => s.category));
  const afterCats = new Set((after.signals ?? []).map((s) => s.category));
  const addedSignals = [...afterCats].filter((c) => !beforeCats.has(c));
  const removedSignals = [...beforeCats].filter((c) => !afterCats.has(c));
  const samePrimary = before.category === after.category;
  const severityBefore = severityRank(before.severity);
  const severityAfter = severityRank(after.severity);
  const severityDelta =
    severityAfter === severityBefore ? "unchanged" : severityAfter < severityBefore ? "improved" : "worsened";

  let outcome;
  if (samePrimary && addedSignals.length === 0 && removedSignals.length === 0) {
    outcome = "same-incident";
  } else if (samePrimary) {
    outcome = "same-primary-shifted-signals";
  } else {
    outcome = "primary-changed";
  }

  const narrative = buildCompareNarrative({
    outcome,
    before,
    after,
    addedSignals,
    removedSignals,
    severityDelta,
  });

  return {
    outcome,
    samePrimary,
    severityDelta,
    before: {
      category: before.category,
      severity: before.severity,
      confidence: before.confidence,
      summary: before.summary,
    },
    after: {
      category: after.category,
      severity: after.severity,
      confidence: after.confidence,
      summary: after.summary,
    },
    addedSignals,
    removedSignals,
    narrative,
  };
}

function buildCompareNarrative({ outcome, before, after, addedSignals, removedSignals, severityDelta }) {
  if (outcome === "same-incident") {
    return `Same primary incident (${before.category}). Severity ${severityDelta}. Treat as the same failure class until new evidence appears.`;
  }
  if (outcome === "same-primary-shifted-signals") {
    const bits = [];
    if (removedSignals.length) bits.push(`cleared: ${removedSignals.join(", ")}`);
    if (addedSignals.length) bits.push(`new: ${addedSignals.join(", ")}`);
    return `Primary still ${before.category}, but secondary signals shifted (${bits.join("; ")}). Severity ${severityDelta}.`;
  }
  return `Primary changed: ${before.category} → ${after.category}. Severity ${severityDelta}. Re-check assumptions before closing the original incident.`;
}
