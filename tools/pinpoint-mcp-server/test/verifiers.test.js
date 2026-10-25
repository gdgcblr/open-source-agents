import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scan } from '../scripts/verify-offline.js';
import { scanSecrets } from '../scripts/secret-scan.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('T-OFF-1: offline verifier reports file:line for forbidden imports, fetch, dynamic import and console.log', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-off-'));
  try {
    fs.writeFileSync(
      path.join(dir, 'bad.js'),
      ["import http from 'node:http';", 'console.log("protocol corruption");', 'await fetch("https://example.test");', "const m = await import('./x.js');", ''].join('\n'),
    );
    const findings = scan(dir);
    const hits = findings.map((f) => `${path.basename(f.file)}:${f.line}`).sort();
    assert.deepEqual(hits, ['bad.js:1', 'bad.js:2', 'bad.js:3', 'bad.js:4']);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('T-OFF-2: real src/ is offline-clean and the package contains no key-shaped secrets', () => {
  assert.deepEqual(scan(path.join(ROOT, 'src')), []);
  assert.deepEqual(scanSecrets(ROOT), []);
});

test('T-OFF-1b: secret scanner flags a key built at runtime in a fixture and masks it', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-secret-'));
  try {
    const key = ['s', 'k-'].join('') + 'FAKE'.repeat(6);
    fs.writeFileSync(path.join(dir, 'config.txt'), `token=${key}\n`);
    const hits = scanSecrets(dir);
    assert.equal(hits.length, 1);
    assert.equal(hits[0].type, 'openai_key');
    assert.equal(hits[0].masked.includes(key), false, 'output must not echo the secret');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
