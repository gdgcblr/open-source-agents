// Native export/import bundles (FR-9). Reads only from DATA_DIR/imports, writes only to
// DATA_DIR/exports, both through safeFileName (G6). Size capped; invalid records quarantined (G12).

import fs from 'node:fs';
import path from 'node:path';
import { BUNDLE_KIND, BUNDLE_SCHEMA_VERSION, MAX_IMPORT_BYTES, MAX_SESSIONS } from './constants.js';
import { GuardError, safeFileName } from './guardrails.js';
import { validateSession } from './schema.js';
import { StoreError } from './store.js';

export const IMPORTS_DIR = 'imports';
export const EXPORTS_DIR = 'exports';

/** Build the bundle text for one session, or for every session when sessionId is omitted. */
export function buildBundle(snapshot, { sessionId, now }) {
  const all = Object.values(snapshot.sessions);
  let sessions = all;
  if (sessionId !== undefined) {
    const one = snapshot.sessions[sessionId];
    if (!one) throw new StoreError('SESSION_NOT_FOUND', 'no such session');
    sessions = [one];
  }
  const bundle = {
    kind: BUNDLE_KIND,
    schema: BUNDLE_SCHEMA_VERSION,
    exportedAt: new Date(now).toISOString(),
    sessions,
  };
  const text = JSON.stringify(bundle, null, 2);
  if (Buffer.byteLength(text, 'utf8') > MAX_IMPORT_BYTES) {
    throw new StoreError('STORE_FULL', 'export exceeds the import size limit; export a single session');
  }
  const counts = {
    sessions: sessions.length,
    messages: sessions.reduce((n, s) => n + s.messages.length, 0),
    pins: sessions.reduce((n, s) => n + s.pins.length, 0),
  };
  return { text, counts };
}

/** Write an export into DATA_DIR/exports. Never overwrites an existing file. */
export function writeExport(dataDir, fileName, text) {
  const dir = path.join(dataDir, EXPORTS_DIR);
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (error) {
    throw new StoreError('STORAGE_ERROR', `cannot create exports folder: ${error.code ?? error.name}`);
  }
  const target = safeFileName(fileName, dir);
  try {
    fs.writeFileSync(target, text, { encoding: 'utf8', flag: 'wx' });
  } catch (error) {
    if (error.code === 'EEXIST') throw new GuardError('PATH_REJECTED', 'export file already exists');
    throw new StoreError('STORAGE_ERROR', `write failed: ${error.code ?? error.name}`);
  }
  return { path: target, bytes: Buffer.byteLength(text, 'utf8') };
}

/** Read an import from DATA_DIR/imports. Size is checked before the file is read. */
export function readImport(dataDir, fileName) {
  const dir = path.join(dataDir, IMPORTS_DIR);
  const target = safeFileName(fileName, dir);
  let stat;
  try {
    stat = fs.statSync(target);
  } catch (error) {
    if (error.code === 'ENOENT') throw new StoreError('NOT_FOUND', 'no import file with that name');
    throw new StoreError('STORAGE_ERROR', `read failed: ${error.code ?? error.name}`);
  }
  if (stat.size > MAX_IMPORT_BYTES) throw new StoreError('IMPORT_INVALID', 'bundle exceeds the import size limit');
  try {
    return fs.readFileSync(target, 'utf8');
  } catch (error) {
    throw new StoreError('STORAGE_ERROR', `read failed: ${error.code ?? error.name}`);
  }
}

/**
 * Parse and validate a bundle. Whole-file problems throw IMPORT_INVALID. Individual invalid
 * sessions are returned in `rejected` so the caller can quarantine them (never dropped silently).
 */
export function parseBundle(text) {
  if (Buffer.byteLength(text, 'utf8') > MAX_IMPORT_BYTES) {
    throw new StoreError('IMPORT_INVALID', 'bundle exceeds the import size limit');
  }
  let raw;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new StoreError('IMPORT_INVALID', 'bundle is not valid JSON');
  }
  if (raw === null || typeof raw !== 'object' || raw.kind !== BUNDLE_KIND) {
    throw new StoreError('IMPORT_INVALID', 'not a pinpoint-mcp export bundle');
  }
  if (raw.schema !== BUNDLE_SCHEMA_VERSION) throw new StoreError('IMPORT_INVALID', 'unsupported bundle schema');
  if (!Array.isArray(raw.sessions)) throw new StoreError('IMPORT_INVALID', 'bundle has no sessions array');
  if (raw.sessions.length > MAX_SESSIONS) throw new StoreError('IMPORT_INVALID', 'bundle has too many sessions');

  const sessions = [];
  const rejected = [];
  raw.sessions.forEach((child, index) => {
    const result = validateSession(child, `bundle.sessions[${index}]`);
    if (!result.ok) {
      rejected.push({ path: result.error.path, message: result.error.message, record: child });
      return;
    }
    rejected.push(...result.rejected);
    sessions.push(result.value);
  });
  return { sessions, rejected };
}

/**
 * Save the whole current store before a replace. Not size-capped: a replace must never be
 * the reason user data is lost, even when the store is larger than one import may be.
 */
export function backupCurrent(dataDir, snapshot, now) {
  const bundle = {
    kind: BUNDLE_KIND,
    schema: BUNDLE_SCHEMA_VERSION,
    exportedAt: new Date(now).toISOString(),
    sessions: Object.values(snapshot.sessions),
  };
  return writeExport(dataDir, `pre-replace-${now}`, JSON.stringify(bundle, null, 2));
}
