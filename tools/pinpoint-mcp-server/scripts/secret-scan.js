// Scan the package for key-shaped secrets. Matches are masked in output. Exit 1 on any hit.
// Excluded: node_modules, .git, .data, coverage. Fake keys are built at runtime in tests, so none appear as literals.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PATTERNS = [
  ['private_key', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ['openai_key', /\bsk-[A-Za-z0-9_-]{20,}/],
  ['google_key', /\bAIza[0-9A-Za-z_-]{35}\b/],
  ['aws_key', /\bAKIA[0-9A-Z]{16}\b/],
  ['github_token', /\bgh[pousr]_[A-Za-z0-9]{36,}\b/],
  ['slack_token', /\bxox[abpr]-[A-Za-z0-9-]{10,}/],
];
const SKIP_DIRS = new Set(['node_modules', '.git', '.data', 'coverage']);
const BINARY_EXT = /\.(png|jpg|jpeg|gif|ico|zip|gz|woff2?)$/i;

const mask = (s) => (s.length <= 8 ? '****' : `${s.slice(0, 4)}…${s.slice(-2)} (${s.length} chars)`);

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name), out);
    } else if (!BINARY_EXT.test(entry.name)) {
      out.push(path.join(dir, entry.name));
    }
  }
  return out;
}

/** Return [{ file, line, type, masked }] for every key-shaped match under root. */
export function scanSecrets(root) {
  const hits = [];
  for (const file of walk(root)) {
    const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
    lines.forEach((text, index) => {
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
  for (const h of hits) {
    process.stdout.write(`${path.relative(root, h.file)}:${h.line}: ${h.type}: ${h.masked}\n`);
  }
  process.stdout.write(hits.length === 0 ? 'scan:secrets OK\n' : `scan:secrets FAILED: ${hits.length} hit(s)\n`);
  process.exit(hits.length === 0 ? 0 : 1);
}
