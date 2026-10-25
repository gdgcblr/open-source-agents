// Static check: src/ must not import network or process APIs, call fetch/WebSocket, use dynamic
// import(), or write to stdout with console.log (stdout is the MCP protocol channel). Exit 1 on any hit.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const FORBIDDEN = [
  { re: /(?:from\s+|import\s*\(\s*|require\s*\(\s*)['"](?:node:)?(?:http|https|http2|net|tls|dgram|dns|child_process|worker_threads)['"]/, why: 'forbidden module import' },
  { re: /\bfetch\s*\(/, why: 'fetch() is forbidden' },
  { re: /\bWebSocket\b/, why: 'WebSocket is forbidden' },
  { re: /\bXMLHttpRequest\b/, why: 'XMLHttpRequest is forbidden' },
  { re: /\bEventSource\b/, why: 'EventSource is forbidden' },
  { re: /(?<![\w.])import\s*\(/, why: 'dynamic import() is forbidden' },
  { re: /\bconsole\.log\s*\(/, why: 'console.log writes to stdout (protocol channel)' },
];

function listJs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith('.js')) out.push(full);
  }
  return out;
}

/** Return [{ file, line, why, text }] for every forbidden construct under dir. */
export function scan(dir) {
  const findings = [];
  for (const file of listJs(dir)) {
    const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
    lines.forEach((text, index) => {
      if (text.trim().startsWith('//')) return;
      for (const rule of FORBIDDEN) {
        if (rule.re.test(text)) findings.push({ file, line: index + 1, why: rule.why, text: text.trim() });
      }
    });
  }
  return findings;
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = path.resolve(HERE, '..', 'src');
  let findings;
  try {
    findings = scan(target);
  } catch (error) {
    process.stdout.write(`verify:offline FAILED: cannot read ${target}: ${error.code ?? error.message}\n`);
    process.exit(1);
  }
  for (const f of findings) {
    process.stdout.write(`${path.relative(process.cwd(), f.file)}:${f.line}: ${f.why}: ${f.text}\n`);
  }
  process.stdout.write(findings.length === 0 ? `verify:offline OK (${target})\n` : `verify:offline FAILED: ${findings.length} finding(s)\n`);
  process.exit(findings.length === 0 ? 0 : 1);
}
