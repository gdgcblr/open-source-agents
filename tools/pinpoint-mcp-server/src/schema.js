// Hand-written storage-boundary validators (G1). They NEVER throw: every result is
// { ok: true, value } or { ok: false, error: { path, message } }. Unknown keys are stripped,
// text is clamped and control characters removed (G2).

import {
  MAX_LABEL_CHARS,
  MAX_MESSAGE_CHARS,
  MAX_MESSAGES_PER_SESSION,
  MAX_NOTE_CHARS,
  MAX_PINS_PER_SESSION,
  MAX_SNIPPET_CHARS,
  MAX_TAG_CHARS,
  MAX_TAGS,
  MAX_TITLE_CHARS,
  SCHEMA_VERSION,
} from './constants.js';
import { clampText, stripControlChars } from './text.js';

export const ROLES = Object.freeze(['user', 'assistant', 'tool', 'unknown']);
export const PIN_KINDS = Object.freeze(['pin', 'bookmark']);

const HEX8 = /^[0-9a-f]{8}$/;
const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isFiniteNumber = (v) => typeof v === 'number' && Number.isFinite(v);
const isNonNegInt = (v) => Number.isInteger(v) && v >= 0;

const fail = (path, message) => ({ ok: false, error: { path, message } });
const pass = (value) => ({ ok: true, value });

/** Clean free text: must be a string or null/undefined; strips control chars and clamps. */
function cleanText(raw, path, max, { nullable = true } = {}) {
  if (raw === undefined || raw === null) {
    return nullable ? pass(null) : fail(path, 'required string');
  }
  if (typeof raw !== 'string') return fail(path, 'must be a string');
  return pass(clampText(stripControlChars(raw), max));
}

function cleanTags(raw, path) {
  if (raw === undefined || raw === null) return pass([]);
  if (!Array.isArray(raw)) return fail(path, 'must be an array');
  if (raw.length > MAX_TAGS) return fail(path, `over ${MAX_TAGS} items`);
  const tags = [];
  for (const tag of raw) {
    if (typeof tag !== 'string') return fail(path, 'tags must be strings');
    const clean = clampText(stripControlChars(tag).trim(), MAX_TAG_CHARS);
    if (clean.length > 0) tags.push(clean);
  }
  return pass(tags);
}

export function validateMessage(raw, path = 'message') {
  try {
    if (!isPlainObject(raw)) return fail(path, 'must be an object');
    if (typeof raw.messageId !== 'string' || !raw.messageId.startsWith('m_')) {
      return fail(`${path}.messageId`, 'must be a m_ id');
    }
    if (!isNonNegInt(raw.ordinal)) return fail(`${path}.ordinal`, 'must be an integer >= 0');
    if (!ROLES.includes(raw.role)) return fail(`${path}.role`, 'unknown role');
    if (typeof raw.text !== 'string') return fail(`${path}.text`, 'must be a string');
    if (typeof raw.textHash !== 'string' || !HEX8.test(raw.textHash)) {
      return fail(`${path}.textHash`, 'must be 8 hex chars');
    }
    if (!isNonNegInt(raw.textLength)) return fail(`${path}.textLength`, 'must be an integer >= 0');
    if (!isFiniteNumber(raw.createdAt)) return fail(`${path}.createdAt`, 'must be a number');
    return pass({
      messageId: raw.messageId,
      ordinal: raw.ordinal,
      role: raw.role,
      text: clampText(stripControlChars(raw.text), MAX_MESSAGE_CHARS),
      textHash: raw.textHash,
      textLength: raw.textLength,
      redacted: raw.redacted === true,
      suspicious: raw.suspicious === true,
      createdAt: raw.createdAt,
    });
  } catch (error) {
    return fail(path, `unexpected: ${error.name}`);
  }
}

export function validatePin(raw, path = 'pin') {
  try {
    if (!isPlainObject(raw)) return fail(path, 'must be an object');
    if (typeof raw.pinId !== 'string' || !raw.pinId.startsWith('p_')) {
      return fail(`${path}.pinId`, 'must be a p_ id');
    }
    if (!PIN_KINDS.includes(raw.kind)) return fail(`${path}.kind`, 'must be pin or bookmark');
    if (raw.messageId !== null && raw.messageId !== undefined && typeof raw.messageId !== 'string') {
      return fail(`${path}.messageId`, 'must be a string or null');
    }
    if (typeof raw.targetHash !== 'string' || !HEX8.test(raw.targetHash)) {
      return fail(`${path}.targetHash`, 'must be 8 hex chars');
    }
    if (!ROLES.includes(raw.role)) return fail(`${path}.role`, 'unknown role');
    if (!isNonNegInt(raw.ordinal)) return fail(`${path}.ordinal`, 'must be an integer >= 0');
    if (!isNonNegInt(raw.textLength)) return fail(`${path}.textLength`, 'must be an integer >= 0');
    if (!isFiniteNumber(raw.order)) return fail(`${path}.order`, 'must be a number');
    if (!isFiniteNumber(raw.createdAt) || !isFiniteNumber(raw.updatedAt)) {
      return fail(`${path}.createdAt`, 'timestamps must be numbers');
    }
    if (!isNonNegInt(raw.repairCount)) return fail(`${path}.repairCount`, 'must be an integer >= 0');

    const snippet = cleanText(raw.snippet ?? '', `${path}.snippet`, MAX_SNIPPET_CHARS, { nullable: false });
    if (!snippet.ok) return snippet;
    const label = cleanText(raw.label, `${path}.label`, MAX_LABEL_CHARS);
    if (!label.ok) return label;
    const note = cleanText(raw.note, `${path}.note`, MAX_NOTE_CHARS);
    if (!note.ok) return note;
    const tags = cleanTags(raw.tags, `${path}.tags`);
    if (!tags.ok) return tags;

    if (raw.kind === 'bookmark' && !label.value) {
      return fail(`${path}.label`, 'bookmark requires a label');
    }
    return pass({
      pinId: raw.pinId,
      kind: raw.kind,
      messageId: raw.messageId ?? null,
      targetHash: raw.targetHash,
      role: raw.role,
      snippet: snippet.value,
      textLength: raw.textLength,
      ordinal: raw.ordinal,
      label: label.value,
      note: note.value,
      tags: tags.value,
      order: raw.order,
      createdAt: raw.createdAt,
      updatedAt: raw.updatedAt,
      repairCount: raw.repairCount,
    });
  } catch (error) {
    return fail(path, `unexpected: ${error.name}`);
  }
}

/**
 * Validate one session. Invalid child messages/pins are dropped and returned in `rejected`
 * so the store can quarantine them (G12). Overflow beyond caps is rejected the same way.
 */
export function validateSession(raw, path = 'session') {
  try {
    if (!isPlainObject(raw)) return fail(path, 'must be an object');
    if (typeof raw.sessionId !== 'string' || !raw.sessionId.startsWith('s_')) {
      return fail(`${path}.sessionId`, 'must be a s_ id');
    }
    if (!isFiniteNumber(raw.createdAt) || !isFiniteNumber(raw.updatedAt)) {
      return fail(`${path}.createdAt`, 'timestamps must be numbers');
    }
    const title = cleanText(raw.title, `${path}.title`, MAX_TITLE_CHARS);
    if (!title.ok) return title;
    if (raw.messages !== undefined && !Array.isArray(raw.messages)) {
      return fail(`${path}.messages`, 'must be an array');
    }
    if (raw.pins !== undefined && !Array.isArray(raw.pins)) {
      return fail(`${path}.pins`, 'must be an array');
    }

    const rejected = [];
    const messages = [];
    for (const [index, child] of (raw.messages ?? []).entries()) {
      const result = validateMessage(child, `${path}.messages[${index}]`);
      if (result.ok && messages.length < MAX_MESSAGES_PER_SESSION) messages.push(result.value);
      else rejected.push({ path: `${path}.messages[${index}]`, message: result.ok ? 'over cap' : result.error.message, record: child });
    }
    const pins = [];
    for (const [index, child] of (raw.pins ?? []).entries()) {
      const result = validatePin(child, `${path}.pins[${index}]`);
      if (result.ok && pins.length < MAX_PINS_PER_SESSION) pins.push(result.value);
      else rejected.push({ path: `${path}.pins[${index}]`, message: result.ok ? 'over cap' : result.error.message, record: child });
    }
    return {
      ok: true,
      value: {
        sessionId: raw.sessionId,
        title: title.value,
        createdAt: raw.createdAt,
        updatedAt: raw.updatedAt,
        messages,
        pins,
        ...(isPlainObject(raw.source) ? { source: pickSource(raw.source) } : {}),
      },
      rejected,
    };
  } catch (error) {
    return fail(path, `unexpected: ${error.name}`);
  }
}

function pickSource(source) {
  const pick = (v) => (typeof v === 'string' ? clampText(stripControlChars(v), 2048) : null);
  return { hostId: pick(source.hostId), threadId: pick(source.threadId), url: pick(source.url) };
}

/**
 * Validate a whole store document. Returns the cleaned store plus rejected records.
 * Only a structurally broken root (not an object / wrong kind / wrong schema) fails outright.
 */
export function validateStore(raw) {
  try {
    if (!isPlainObject(raw)) return fail('store', 'must be an object');
    if (raw.kind !== 'pinpoint-mcp-store') return fail('store.kind', 'wrong kind');
    if (raw.schema !== SCHEMA_VERSION) return fail('store.schema', 'unsupported schema version');
    if (!isPlainObject(raw.sessions)) return fail('store.sessions', 'must be an object');

    const rejected = [];
    const sessions = {};
    for (const [key, child] of Object.entries(raw.sessions)) {
      const result = validateSession(child, `store.sessions.${key}`);
      if (!result.ok) {
        rejected.push({ path: result.error.path, message: result.error.message, record: child });
        continue;
      }
      rejected.push(...result.rejected);
      sessions[result.value.sessionId] = result.value;
    }
    return {
      ok: true,
      value: { kind: 'pinpoint-mcp-store', schema: SCHEMA_VERSION, sessions },
      rejected,
    };
  } catch (error) {
    return fail('store', `unexpected: ${error.name}`);
  }
}
