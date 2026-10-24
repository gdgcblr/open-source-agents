import { constants } from 'node:fs';
import { open, type FileHandle } from 'node:fs/promises';
import type { LogEvent } from './types.js';
import { SPAN_KINDS } from './types.js';

const MAX_READ_BYTES = 64 * 1024 * 1024;

/** Args: local JSONL path. Returns: validated events. Raises: on unsafe file, invalid schema or I/O failure. */
export async function readLog(filePath: string): Promise<readonly LogEvent[]> {
  const file = await open(
    filePath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const metadata = await file.stat();
    if (!metadata.isFile() || metadata.size > MAX_READ_BYTES)
      throw new Error('Expected a regular log file no larger than 64 MiB.');
    const text = await readBounded(file, metadata.size);
    return text
      .split('\n')
      .filter((line) => line.trim() !== '')
      .map(parseEvent);
  } finally {
    await file.close();
  }
}

async function readBounded(file: FileHandle, size: number): Promise<string> {
  const buffer = Buffer.alloc(size + 1);
  let total = 0;
  while (total < buffer.length) {
    const { bytesRead } = await file.read(buffer, total, buffer.length - total, total);
    if (!bytesRead) break;
    total += bytesRead;
  }
  if (total > size)
    throw new Error('Log is still being written; close the logger before reading it.');
  return buffer.subarray(0, total).toString('utf8');
}

function parseEvent(line: string): LogEvent {
  const event: unknown = JSON.parse(line);
  if (!event || typeof event !== 'object') throw new Error('Invalid log event.');
  const record = event as Record<string, unknown>;
  validateOptionalFields(record);
  validateIdentity(record);
  validateLifecycle(record);
  return event as LogEvent;
}

function validateOptionalFields(record: Record<string, unknown>): void {
  if (
    record.durationMs !== undefined &&
    (typeof record.durationMs !== 'number' ||
      !Number.isFinite(record.durationMs) ||
      record.durationMs < 0)
  )
    throw new Error('Invalid duration.');
  if (
    record.parentSpanId !== undefined &&
    (typeof record.parentSpanId !== 'string' ||
      !/^[a-f0-9-]{36}$/i.test(record.parentSpanId))
  )
    throw new Error('Invalid parent span.');
}

function validateIdentity(record: Record<string, unknown>): void {
  const identifiers = [record.runId, record.spanId];
  const validIds = identifiers.every(
    (id) => typeof id === 'string' && /^[a-f0-9-]{36}$/i.test(id),
  );
  if (
    record.schemaVersion !== 1 ||
    !validIds ||
    !Number.isSafeInteger(record.sequence) ||
    (record.sequence as number) < 1
  )
    throw new Error('Unsupported or invalid log event.');
  if (
    typeof record.name !== 'string' ||
    record.name.length > 128 ||
    typeof record.timestamp !== 'string' ||
    !Number.isFinite(Date.parse(record.timestamp))
  )
    throw new Error('Invalid log event labels.');
}

function validateLifecycle(record: Record<string, unknown>): void {
  if (
    typeof record.kind !== 'string' ||
    !(SPAN_KINDS as readonly string[]).includes(record.kind) ||
    typeof record.phase !== 'string' ||
    !['started', 'finished'].includes(record.phase)
  )
    throw new Error('Invalid log event lifecycle.');
  if (
    (record.phase === 'finished' || record.status !== undefined) &&
    (typeof record.status !== 'string' ||
      !['completed', 'failed', 'interrupted'].includes(record.status))
  )
    throw new Error('Invalid terminal log status.');
}
