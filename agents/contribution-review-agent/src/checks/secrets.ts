import {type CheckResult, type Finding, toResult} from '../types.js';

const SECRET_PATTERNS: {name: string; regex: RegExp}[] = [
  {name: 'Google API key', regex: /\bAIza[0-9A-Za-z_-]{35}/},
  {name: 'Anthropic API key', regex: /\bsk-ant-[A-Za-z0-9_-]{20,}/},
  {name: 'OpenAI API key', regex: /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/},
  {name: 'GitHub token', regex: /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})/},
  {name: 'AWS access key ID', regex: /\bAKIA[0-9A-Z]{16}\b/},
  {name: 'Slack token', regex: /\bxox[abprs]-[A-Za-z0-9-]{10,}/},
  {name: 'Private key', regex: /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----/},
];
const HARDCODED_ASSIGNMENT = /(?:api[_-]?key|secret|token|password)["']?\s*[:=]\s*["']([^"'\s]{20,})["']/i;
const PLACEHOLDER_HINT = /your|example|placeholder|changeme|dummy|xxxx|<|\$\{/i;

const FORBIDDEN_FILES: {test: RegExp; reason: string}[] = [
  {test: /(?:^|\/)\.env(?:\.(?!example$)[^/]+)?$/, reason: 'an environment file that may contain real values'},
  {test: /\.(?:pem|key|p12|pfx)$/, reason: 'a private key or certificate'},
  {test: /(?:^|\/)(?:credentials\.json|service-account[^/]*\.json)$/, reason: 'a cloud credentials file'},
];
const FORBIDDEN_DIRS = /(?:^|\/)(node_modules|\.venv|venv|__pycache__)\//;
const SKIP_SCAN = /\.(?:png|jpe?g|gif|webp|ico|pdf|zip|gz|tar|mp[34]|woff2?|ttf|eot)$|(?:^|\/)(?:package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$/i;
const MAX_FINDINGS = 50;

function mask(value: string): string {
  return `${value.slice(0, 4)}${'*'.repeat(8)}`;
}

export function scanText(path: string, text: string): Finding[] {
  const findings: Finding[] = [];
  text.split('\n').forEach((line, i) => {
    const where = `\`${path}:${i + 1}\``;
    const hit = SECRET_PATTERNS.find((p) => p.regex.test(line));
    if (hit) {
      const value = line.match(hit.regex)![0];
      findings.push({
        severity: 'error',
        message: `${where} looks like a ${hit.name} (${mask(value)}).`,
        fix: 'Remove it, rotate the key, and load it from an environment variable instead.',
      });
      return;
    }
    const assigned = line.match(HARDCODED_ASSIGNMENT);
    if (assigned && !PLACEHOLDER_HINT.test(assigned[1])) {
      findings.push({
        severity: 'warning',
        message: `${where} may contain a hardcoded credential (${mask(assigned[1])}).`,
        fix: 'Load secrets from environment variables.',
      });
    }
  });
  return findings;
}

export async function scanSecrets(
  files: string[],
  readFile: (path: string) => Promise<string | null>,
): Promise<CheckResult> {
  const findings: Finding[] = [];
  const flaggedDirs = new Set<string>();

  for (const file of files) {
    const dir = file.match(FORBIDDEN_DIRS);
    if (dir) {
      if (!flaggedDirs.has(dir[1])) {
        flaggedDirs.add(dir[1]);
        findings.push({
          severity: 'error',
          message: `\`${dir[1]}/\` would be committed.`,
          fix: `Add \`${dir[1]}/\` to \`.gitignore\`.`,
        });
      }
      continue;
    }
    const forbidden = FORBIDDEN_FILES.find((f) => f.test.test(file));
    if (forbidden) {
      findings.push({
        severity: 'error',
        message: `\`${file}\` is ${forbidden.reason} and would be committed.`,
        fix: 'Delete it from the commit and add it to `.gitignore`.',
      });
      continue;
    }
    if (SKIP_SCAN.test(file)) continue;
    const text = await readFile(file);
    if (text) findings.push(...scanText(file, text));
    if (findings.length >= MAX_FINDINGS) break;
  }
  return toResult('Secrets & tracked files', findings.slice(0, MAX_FINDINGS));
}
