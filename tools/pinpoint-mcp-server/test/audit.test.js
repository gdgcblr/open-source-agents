import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createAudit } from '../src/audit.js';

const SECRET = ['s', 'k-'].join('') + 'FAKE'.repeat(6) + '00';
const MESSAGE = 'MESSAGE-TEXT-MARKER-4f2a';

test('T-AUD-1: audit log never contains raw args, secrets, or message text', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-audit-'));
  try {
    const audit = createAudit({ dataDir: dir, clock: () => 1000 });
    audit.record({
      tool: 'record_message',
      sessionId: 's_1',
      ok: true,
      durationMs: 3,
      args: { text: `${MESSAGE} ${SECRET}` },
      redacted: true,
      suspicious: false,
      correlationId: 'c_1',
    });
    const log = fs.readFileSync(path.join(dir, 'audit.jsonl'), 'utf8');
    assert.equal(log.includes(SECRET), false);
    assert.equal(log.includes(MESSAGE), false);
    const line = JSON.parse(log.trim());
    assert.match(line.argsHash, /^[0-9a-f]{8}$/);
    assert.equal(line.tool, 'record_message');
    assert.equal(line.redacted, true);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('T-AUD-2: write failure is logged to stderr and never thrown', () => {
  const missing = path.join(os.tmpdir(), 'pinpoint-audit-missing-', String(Date.now()), 'nope');
  const audit = createAudit({ dataDir: missing });
  const original = process.stderr.write.bind(process.stderr);
  let stderrText = '';
  process.stderr.write = (chunk) => {
    stderrText += String(chunk);
    return true;
  };
  try {
    assert.doesNotThrow(() => audit.record({ tool: 'health', ok: true }));
  } finally {
    process.stderr.write = original;
  }
  assert.match(stderrText, /audit write failed/);
});
