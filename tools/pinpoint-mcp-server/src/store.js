// JSON store with a single in-process writer (brief §6.4).
// Every mutation: serialise through a promise-chain mutex, clone, apply, validate, write
// `store.json.tmp`, rename over `store.json`. A failure leaves the previous file untouched.

import fs from 'node:fs';
import path from 'node:path';
import {
  AUDIT_FILE,
  LOCK_TIMEOUT_MS,
  MAX_MESSAGES_PER_SESSION,
  MAX_PINS_PER_SESSION,
  MAX_SESSIONS,
  MAX_STORE_BYTES,
  MAX_TITLE_CHARS,
  QUARANTINE_FILE,
  SCHEMA_VERSION,
  STORE_FILE,
} from './constants.js';
import { newId } from './ids.js';
import { validateStore } from './schema.js';
import { clampText, stripControlChars } from './text.js';

/** Typed, expected error. Anything else is an internal bug (G11). */
export class StoreError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'StoreError';
    this.code = code;
  }
}

const defaultIo = {
  readFileSync: (p) => fs.readFileSync(p, 'utf8'),
  writeFileSync: (p, data) => fs.writeFileSync(p, data, 'utf8'),
  renameSync: (from, to) => fs.renameSync(from, to),
  existsSync: (p) => fs.existsSync(p),
  unlinkSync: (p) => fs.unlinkSync(p),
};

const emptyStore = () => ({ kind: 'pinpoint-mcp-store', schema: SCHEMA_VERSION, sessions: {} });

function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve('timeout'), ms);
  });
  return Promise.race([promise.then(() => 'go'), timeout]).finally(() => clearTimeout(timer));
}

/**
 * @param {object} opts
 * @param {string} opts.dataDir
 * @param {() => number} [opts.clock]
 * @param {{ error: Function, warn: Function, info: Function, debug: Function }} opts.logger
 * @param {object} [opts.io]  filesystem seam (tests inject failures)
 * @param {number} [opts.maxStoreBytes]
 * @param {number} [opts.lockTimeoutMs]
 */
export function createStore({
  dataDir,
  clock = Date.now,
  logger,
  io = defaultIo,
  maxStoreBytes = MAX_STORE_BYTES,
  lockTimeoutMs = LOCK_TIMEOUT_MS,
}) {
  const storePath = path.join(dataDir, STORE_FILE);
  const quarantinePath = path.join(dataDir, QUARANTINE_FILE);
  const health = { lastCorruptionEvent: null, quarantined: 0 };
  let state = emptyStore();
  let tail = Promise.resolve();

  function recordCorruption(reason, extra = {}) {
    const preserved = `store.corrupt-${clock()}.json`;
    try {
      io.renameSync(storePath, path.join(dataDir, preserved));
    } catch (error) {
      logger.error('could not preserve corrupt store', { error: error.message });
    }
    health.lastCorruptionEvent = { at: new Date(clock()).toISOString(), reason, file: preserved, ...extra };
    logger.warn('store corrupt; started empty and preserved the file', { reason });
  }

  function quarantine(rejected) {
    if (rejected.length === 0) return;
    health.quarantined += rejected.length;
    let existing = [];
    try {
      if (io.existsSync(quarantinePath)) existing = JSON.parse(io.readFileSync(quarantinePath));
    } catch {
      existing = [];
    }
    const entries = Array.isArray(existing) ? existing : [];
    const stamp = new Date(clock()).toISOString();
    for (const item of rejected) entries.push({ at: stamp, path: item.path, message: item.message, record: item.record });
    try {
      io.writeFileSync(quarantinePath, JSON.stringify(entries, null, 2));
    } catch (error) {
      logger.error('could not write quarantine file', { error: error.message });
    }
  }

  /** Load from disk. Never deletes data (R6). Safe to call once at startup. */
  function load() {
    let raw;
    try {
      if (!io.existsSync(storePath)) {
        state = emptyStore();
        return health;
      }
      raw = io.readFileSync(storePath);
    } catch (error) {
      // Read failures (EACCES, EIO, ...) are not corruption: leave the file in place.
      logger.error('could not read store; file left in place', { error: error.message });
      throw new StoreError('STORAGE_ERROR', `read failed: ${error.code ?? error.name}`);
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      recordCorruption('unparseable JSON');
      state = emptyStore();
      return health;
    }
    const checked = validateStore(parsed);
    if (!checked.ok) {
      recordCorruption('invalid store root', { detail: checked.error.message });
      state = emptyStore();
      return health;
    }
    state = checked.value;
    if (checked.rejected.length > 0) {
      quarantine(checked.rejected);
      writeAtomic(state);
    }
    return health;
  }

  function serialise(next) {
    const text = JSON.stringify(next, null, 2);
    if (Buffer.byteLength(text, 'utf8') > maxStoreBytes) {
      throw new StoreError('STORE_FULL', 'store would exceed its size limit');
    }
    return text;
  }

  function writeAtomic(next) {
    const text = serialise(next);
    const tmp = `${storePath}.tmp`;
    try {
      io.writeFileSync(tmp, text);
      io.renameSync(tmp, storePath);
    } catch (error) {
      try {
        if (io.existsSync(tmp)) io.unlinkSync(tmp);
      } catch {
        // best effort cleanup; the previous store.json is untouched either way
      }
      throw new StoreError('STORAGE_ERROR', `write failed: ${error.code ?? error.name}`);
    }
  }

  /**
   * Apply `fn(draft)` atomically. `fn` may throw StoreError for expected failures.
   * Resolves to { ok: true, value } or { ok: false, error: { code, message } }.
   */
  async function mutate(fn) {
    const previous = tail;
    let release;
    tail = new Promise((resolve) => {
      release = resolve;
    });
    let slotHandedOff = false;
    try {
      const turn = await withTimeout(previous, lockTimeoutMs);
      if (turn === 'timeout') {
        // The slow holder may still be writing. Keep our place in the queue until it settles,
        // so later mutations cannot overtake it (lost update). We never run `fn` ourselves.
        slotHandedOff = true;
        previous.finally(release);
        return { ok: false, error: { code: 'LOCK_TIMEOUT', message: 'store is busy' } };
      }
      const draft = structuredClone(state);
      let value;
      try {
        value = await fn(draft);
      } catch (error) {
        if (error instanceof StoreError) return { ok: false, error: { code: error.code, message: error.message } };
        logger.error('mutation failed', { error: error.message });
        return { ok: false, error: { code: 'INTERNAL', message: 'internal error' } };
      }
      const checked = validateStore(draft);
      if (!checked.ok || checked.rejected.length > 0) {
        return { ok: false, error: { code: 'STORAGE_INVALID', message: 'change would produce invalid records' } };
      }
      try {
        writeAtomic(checked.value);
      } catch (error) {
        if (error instanceof StoreError) return { ok: false, error: { code: error.code, message: error.message } };
        throw error;
      }
      state = checked.value;
      return { ok: true, value };
    } finally {
      if (!slotHandedOff) release();
    }
  }

  /** Read-only deep copy. Callers may not mutate the live state through it. */
  function snapshot() {
    return structuredClone(state);
  }

  function requireSession(draft, sessionId) {
    const session = draft.sessions[sessionId];
    if (!session) throw new StoreError('SESSION_NOT_FOUND', 'no such session');
    return session;
  }

  function createSession(title) {
    return mutate((draft) => {
      if (Object.keys(draft.sessions).length >= MAX_SESSIONS) {
        throw new StoreError('LIMIT_SESSIONS', `session limit of ${MAX_SESSIONS} reached`);
      }
      const now = clock();
      const sessionId = newId('s', now);
      draft.sessions[sessionId] = {
        sessionId,
        title: title === undefined || title === null ? null : clampText(stripControlChars(title), MAX_TITLE_CHARS),
        createdAt: now,
        updatedAt: now,
        messages: [],
        pins: [],
      };
      return sessionId;
    });
  }

  function appendMessage(sessionId, fields) {
    return mutate((draft) => {
      const session = requireSession(draft, sessionId);
      if (session.messages.length >= MAX_MESSAGES_PER_SESSION) {
        throw new StoreError('LIMIT_MESSAGES', `message limit of ${MAX_MESSAGES_PER_SESSION} reached`);
      }
      const now = clock();
      const message = {
        messageId: newId('m', now),
        ordinal: session.messages.length,
        createdAt: now,
        ...fields,
      };
      session.messages.push(message);
      session.updatedAt = now;
      return message;
    });
  }

  function addPin(sessionId, pin) {
    return mutate((draft) => {
      const session = requireSession(draft, sessionId);
      if (session.pins.length >= MAX_PINS_PER_SESSION) {
        throw new StoreError('LIMIT_PINS', `pin limit of ${MAX_PINS_PER_SESSION} reached`);
      }
      session.pins.push(pin);
      session.updatedAt = clock();
      return pin;
    });
  }

  return {
    load,
    mutate,
    snapshot,
    quarantine,
    createSession,
    appendMessage,
    addPin,
    health: () => ({ ...health, dataDir, storePath, bytesLimit: maxStoreBytes }),
    auditFile: path.join(dataDir, AUDIT_FILE),
    _state: () => state,
  };
}
