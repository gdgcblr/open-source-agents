/**
 * PR Sentinel - Secret & Credential Scanner Tool
 * Analyzes code content and git diffs for leaked secrets, API keys, and credentials.
 */

export const SECRET_PATTERNS = [
  {
    name: 'Google / Gemini API Key',
    regex: /AIzaSy[0-9A-Za-z\\-_]{33}/g,
    type: 'gemini_api_key',
    severity: 'CRITICAL',
  },
  {
    name: 'OpenAI API Key',
    regex: /sk-(?:live|proj)?[a-zA-Z0-9_\-]{20,60}/g,
    type: 'openai_api_key',
    severity: 'CRITICAL',
  },
  {
    name: 'GitHub Personal Access Token',
    regex: /(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}|github_pat_[A-Za-z0-9_]{60,120}/g,
    type: 'github_token',
    severity: 'CRITICAL',
  },
  {
    name: 'AWS Access Key ID',
    regex: /(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}/g,
    type: 'aws_access_key',
    severity: 'CRITICAL',
  },
  {
    name: 'Slack API Token',
    regex: /xox[baprs]-[0-9a-zA-Z]{10,48}/g,
    type: 'slack_token',
    severity: 'HIGH',
  },
  {
    name: 'Private Key Block',
    regex: /-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY[^-]*-----/g,
    type: 'private_key',
    severity: 'CRITICAL',
  },
  {
    name: 'Generic Bearer / API Key Assignment',
    regex: /(?:api_key|apiKey|secret_key|authToken|bearerToken)\s*[:=]\s*["']([A-Za-z0-9_\-\.]{24,})["']/gi,
    type: 'generic_secret',
    severity: 'HIGH',
  },
];

/**
 * Scan text or diff content for exposed secrets
 * @param {string} content
 * @param {string} filePath
 * @returns {Array<Object>} List of detected secrets
 */
export function scanContentForSecrets(content, filePath = 'unknown') {
  if (!content || typeof content !== 'string') return [];

  const findings = [];
  const lines = content.split('\n');

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const lineText = lines[lineIndex];

    // Skip comment lines in template/example files or explicit tests if annotated
    if (filePath.endsWith('.env.example') || filePath.includes('.test.') || filePath.includes('template/')) {
      // Don't flag placeholders like your_api_key_here
      if (/placeholder|your_.*_key|<your-.*>|sk-demo|AIzaSyDemo/i.test(lineText)) {
        continue;
      }
    }

    for (const pattern of SECRET_PATTERNS) {
      // Reset lastIndex for global regex
      pattern.regex.lastIndex = 0;
      let match;
      while ((match = pattern.regex.exec(lineText)) !== null) {
        const rawMatch = match[0];

        // Filter out obvious harmless placeholders
        if (
          rawMatch.includes('YOUR_') ||
          rawMatch.includes('your_') ||
          rawMatch.includes('EXAMPLE') ||
          rawMatch.includes('placeholder')
        ) {
          continue;
        }

        const masked = maskSecret(rawMatch);

        findings.push({
          type: pattern.type,
          name: pattern.name,
          severity: pattern.severity,
          file: filePath,
          line: lineIndex + 1,
          maskedSecret: masked,
          context: lineText.trim().replace(rawMatch, masked),
        });
      }
    }
  }

  return findings;
}

/**
 * Mask sensitive string for safe presentation
 * @param {string} secret
 * @returns {string}
 */
export function maskSecret(secret) {
  if (secret.length <= 8) return '****';
  const prefix = secret.slice(0, 4);
  const suffix = secret.slice(-4);
  return `${prefix}...${suffix}`;
}

export default {
  SECRET_PATTERNS,
  scanContentForSecrets,
  maskSecret,
};
