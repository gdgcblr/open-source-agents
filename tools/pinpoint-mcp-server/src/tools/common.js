// Shared tool plumbing: uniform success/error envelopes, selector shape, error wrapping and audit.
// Every handler goes through wrapTool, so no tool can leak a stack trace (SR-11).

import { randomBytes } from 'node:crypto';
import { z } from 'zod';
import { DEFAULT_SNIPPET_CHARS, MAX_TITLE_CHARS } from '../constants.js';
import { GuardError, untrusted } from '../guardrails.js';
import { StoreError } from '../store.js';
import { clampText } from '../text.js';

export class ToolError extends Error {
  constructor(code, message, extra = {}) {
    super(message);
    this.name = 'ToolError';
    this.code = code;
    this.extra = extra;
  }
}

export const READ_ONLY = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };
export const WRITE = { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false };
export const DESTRUCTIVE = { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false };

export const sessionIdField = z.string().min(1).describe('Session id returned by start_session');
export const pinIdField = z.string().min(1).describe('Pin id returned by pin_message or bookmark_message');

/** Message selector: supply exactly one of these fields (checked in the handler). */
export const selectorShape = {
  messageId: z.string().optional().describe('Exact message id'),
  ordinal: z.number().int().min(0).optional().describe('Zero-based message position in the session'),
  last: z.enum(['user', 'assistant', 'any']).optional().describe('Most recent message from this role'),
  textQuery: z.string().optional().describe('Text to match against messages; ambiguous matches are refused'),
};

/** Success envelope. Payload fields are spread next to ok:true. */
export function success(payload) {
  return { content: [{ type: 'text', text: JSON.stringify({ ok: true, ...payload }) }] };
}

/** Failure envelope. Used for every handled error. */
export function failure(code, message, extra = {}) {
  const body = { ok: false, error: { code, message, ...extra } };
  return { isError: true, content: [{ type: 'text', text: JSON.stringify(body) }] };
}

/** Throw a ToolError when a store/mutate result failed; return its value otherwise. */
export function unwrap(result) {
  if (result.ok) return result.value;
  throw new ToolError(result.error.code, result.error.message);
}

export function requireTrimmed(value, code, message) {
  if (typeof value !== 'string' || value.trim().length === 0) throw new ToolError(code, message);
  return value.trim();
}

/** Pick only the selector keys the caller actually supplied (undefined keys would count). */
export function pickSelector(args) {
  const out = {};
  for (const key of ['messageId', 'ordinal', 'last', 'textQuery']) {
    if (args[key] !== undefined) out[key] = args[key];
  }
  return out;
}

/** Trim a snippet from message text, bounded by the snippet limit. */
export function makeSnippet(text) {
  return clampText(text, DEFAULT_SNIPPET_CHARS);
}

/** The shape every pin returns to a client. Stored message text is wrapped as untrusted. */
export function summarisePin(pin, sessionId) {
  return {
    pinId: pin.pinId,
    sessionId,
    kind: pin.kind,
    messageId: pin.messageId,
    role: pin.role,
    ordinal: pin.ordinal,
    label: pin.label,
    note: pin.note,
    tags: pin.tags,
    order: pin.order,
    repairCount: pin.repairCount,
    untrustedContent: untrusted(pin.snippet),
  };
}

export const sessionTitle = (title) => (title === null ? null : untrusted(clampText(title, MAX_TITLE_CHARS)));

/** Find a pin across all sessions in a snapshot. */
export function findPin(snapshot, pinId) {
  for (const session of Object.values(snapshot.sessions)) {
    const pin = session.pins.find((p) => p.pinId === pinId);
    if (pin) return { session, pin };
  }
  return null;
}

function correlationId() {
  return randomBytes(6).toString('hex');
}

/**
 * Wrap a tool handler. The handler receives (args, ctx) and returns a payload; it may set
 * ctx.sessionId / ctx.redacted / ctx.suspicious for the audit line. Errors become envelopes.
 */
export function wrapTool(name, { audit, logger }, handler) {
  return async (args = {}) => {
    const started = Date.now();
    const ctx = { sessionId: typeof args.sessionId === 'string' ? args.sessionId : null, redacted: false, suspicious: false };
    let response;
    let errorCode = null;
    let correlation = null;
    try {
      const payload = await handler(args, ctx);
      response = success(payload);
    } catch (error) {
      if (error instanceof ToolError || error instanceof StoreError || error instanceof GuardError) {
        errorCode = error.code;
        response = failure(error.code, error.message, error.extra ?? {});
      } else {
        correlation = correlationId();
        errorCode = 'INTERNAL';
        logger.error('tool failed', { tool: name, correlationId: correlation, error: String(error?.stack ?? error) });
        response = failure('INTERNAL', 'internal error', { correlationId: correlation });
      }
    }
    audit.record({
      tool: name,
      sessionId: ctx.sessionId,
      ok: errorCode === null,
      errorCode,
      durationMs: Date.now() - started,
      args,
      redacted: ctx.redacted,
      suspicious: ctx.suspicious,
      correlationId: correlation,
    });
    return response;
  };
}

export { z };
