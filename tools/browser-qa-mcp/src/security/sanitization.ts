const SENSITIVE_QUERY_PARAMS = [
  "password",
  "token",
  "apikey",
  "api_key",
  "secret",
  "authorization",
  "auth",
  "session",
  "access_token",
];

/**
 * Redacts obvious secrets (bearer tokens, sensitive query-string values) from
 * free-text evidence (console messages, error strings) before it is stored
 * in a report or artifact.
 */
export function sanitizeText(text: string): string {
  let out = text.replace(/Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi, "Bearer [REDACTED]");
  out = out.replace(
    new RegExp(`((?:^|[?&\\s])(?:${SENSITIVE_QUERY_PARAMS.join("|")})=)[^&\\s"']+`, "gi"),
    "$1[REDACTED]",
  );
  return out;
}

/** Redacts sensitive query-string parameter values from a URL before it is stored as evidence. */
export function sanitizeUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    for (const param of SENSITIVE_QUERY_PARAMS) {
      if (url.searchParams.has(param)) {
        url.searchParams.set(param, "[REDACTED]");
      }
    }
    return url.toString();
  } catch {
    return sanitizeText(rawUrl);
  }
}
