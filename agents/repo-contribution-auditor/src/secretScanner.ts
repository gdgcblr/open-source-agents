/**
 * Secret scanner patterns.
 *
 * Produces REDACTED evidence only — raw secret values are never stored or emitted.
 * Patterns are heuristic (regex-based); they catch common forms but are NOT exhaustive.
 *
 * Patterns covered:
 *  - PEM private key blocks
 *  - Google API key shape (AIza...)
 *  - Generic high-entropy assignments (quoted strings ≥ 32 chars with sufficient entropy)
 *  - AWS access key IDs
 *  - GitHub personal access tokens (ghp_, gho_, ghx_)
 */

export interface SecretMatch {
  /** Pattern name */
  pattern: string;
  /** 1-based line number */
  line: number;
  /** Redacted representation — never contains actual secret */
  redactedEvidence: string;
}

/** Shannon entropy of a string (bits per char) */
function shannonEntropy(s: string): number {
  const freq = new Map<string, number>();
  for (const c of s) {
    freq.set(c, (freq.get(c) ?? 0) + 1);
  }
  let entropy = 0;
  for (const count of freq.values()) {
    const p = count / s.length;
    entropy -= p * Math.log2(p);
  }
  return entropy;
}

// Named pattern registry — order matters (more specific first)
const SECRET_PATTERNS: Array<{
  name: string;
  regex: RegExp;
  redact: (match: RegExpMatchArray) => string;
}> = [
  {
    name: "pem-private-key",
    regex: /-----BEGIN\s+(RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/,
    redact: () => "[REDACTED: PEM private key header detected]",
  },
  {
    name: "google-api-key",
    // Google API keys: AIza followed by 35 base64url chars
    regex: /\bAIza[0-9A-Za-z\-_]{35}\b/,
    redact: (m) => `[REDACTED: Google API key shape AIza...${m[0].slice(-4)}]`,
  },
  {
    name: "aws-access-key-id",
    // AWS Access Key IDs start with AKIA and are 20 chars
    regex: /\bAKIA[0-9A-Z]{16}\b/,
    redact: (m) => `[REDACTED: AWS Access Key ID AKIA...${m[0].slice(-4)}]`,
  },
  {
    name: "github-token",
    // GitHub personal/OAuth tokens
    regex: /\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b/,
    redact: (m) => `[REDACTED: GitHub token ${m[1]}_...${m[0].slice(-4)}]`,
  },
  {
    name: "high-entropy-assignment",
    // KEY=  or key:  followed by a quoted/unquoted 32+ char string
    // Only flag if Shannon entropy >= 4.0 bits/char (high randomness)
    regex:
      /(?:secret|api[_-]?key|token|password|passwd|auth|credential)\s*[:=]\s*["']?([A-Za-z0-9+/=_\-]{32,})["']?/i,
    redact: (m) => {
      const val = m[1] ?? "";
      if (shannonEntropy(val) < 4.0) return ""; // not high entropy, skip
      return `[REDACTED: High-entropy assignment (${val.length} chars, entropy≥4)]`;
    },
  },
];

/**
 * Scan a single file's content for secret patterns.
 * Returns an array of matches (may be empty).
 */
export function scanSecrets(content: string): SecretMatch[] {
  const matches: SecretMatch[] = [];
  const lines = content.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    const lineNum = i + 1;

    for (const { name, regex, redact } of SECRET_PATTERNS) {
      const m = line.match(regex);
      if (m) {
        const evidence = redact(m);
        if (!evidence) continue; // entropy check skipped it
        matches.push({
          pattern: name,
          line: lineNum,
          redactedEvidence: evidence,
        });
        break; // one match per line is enough
      }
    }
  }

  return matches;
}
