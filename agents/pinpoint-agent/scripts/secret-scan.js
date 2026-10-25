// Key-shaped secret scan for this package. Matches are masked. Exit 1 on any hit.
// Excludes node_modules, .git, coverage, and .env (the real key lives only there, never committed).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PATTERNS = [
  ['private_key', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ['google_key', /\bAIza[0-9A-Za-z_-]{35}\b/],
  ['openai_key', /\bsk-[A-Za-z0-9_-]{20,}/],
  ['aws_key', /\bAKIA[0-9A-Z]{16}\b/],
  ['github_token', /\bgh[pousr]_[A-Za-z0-9]{36,}\b/],
  ['slack_token', /\bxox[abpr]-[A-Za-z0-9-]{10,}/],
];
const SKIP = new Set(['node_modules', '.git', 'coverage']);
const SKIP_FILES = new Set(['.env']);

const mask = (s) => (s.length <= 8 ? '****' : `${s.slice(0, 4)}…${s.slice(-2)} (${s.length} chars)`);

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP.has(entry.name)) walk(full, out);
    } else if (!SKIP_FILES.has(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

export function scanSecrets(root) {
  const hits = [];
  for (const file of walk(root)) {
    if (/\.(png|jpg|jpeg|gif|zip|gz|woff2?)$/i.test(file)) continue;
    fs.readFileSync(file, 'utf8')
      .split(/\r?\n/)
      .forEach((text, index) => {
        for (const [type, re] of PATTERNS) {
          const match = text.match(re);
          if (match) hits.push({ file, line: index + 1, type, masked: mask(match[0]) });
        }
      });
  }
  return hits;
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(HERE, '..');
  let hits;
  try {
    hits = scanSecrets(root);
  } catch (error) {
    process.stdout.write(`scan:secrets FAILED: cannot read ${root}: ${error.code ?? error.message}\n`);
    process.exit(1);
  }
  for (const h of hits) process.stdout.write(`${path.relative(root, h.file)}:${h.line}: ${h.type}: ${h.masked}\n`);
  process.stdout.write(hits.length === 0 ? 'scan:secrets OK\n' : `scan:secrets FAILED: ${hits.length} hit(s)\n`);
  process.exit(hits.length === 0 ? 0 : 1);
}
