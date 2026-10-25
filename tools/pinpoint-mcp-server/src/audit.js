// Append-only JSONL audit log. Stores a hash of the arguments, never raw args or message text.

import fs from 'node:fs';
import path from 'node:path';
import { fnvHex } from './text.js';

const AUDIT_FILE = 'audit.jsonl';

/**
 * createAudit({ dataDir, enabled, clock }) → { record(entry) }.
 * A write failure is logged to stderr and never thrown.
 */
export function createAudit({ dataDir, enabled = true, clock = Date.now }) {
  const file = path.join(dataDir, AUDIT_FILE);

  function record({ tool, sessionId = null, ok, errorCode = null, durationMs = 0, args = null, redacted = false, suspicious = false, correlationId = null }) {
    if (!enabled) return;
    const line = {
      at: new Date(clock()).toISOString(),
      tool,
      sessionId,
      ok: Boolean(ok),
      errorCode,
      durationMs,
      argsHash: fnvHex(JSON.stringify(args ?? null)),
      redacted: Boolean(redacted),
      suspicious: Boolean(suspicious),
      correlationId,
    };
    try {
      fs.appendFileSync(file, `${JSON.stringify(line)}\n`, 'utf8');
    } catch (error) {
      process.stderr.write(`audit write failed: ${error.code ?? error.message}\n`);
    }
  }

  return { record };
}
