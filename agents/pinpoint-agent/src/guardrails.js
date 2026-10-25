// Guardrails around the model: input clamp, tool allowlist, session injection, confirmation gate,
// call budget, and result truncation that keeps the untrustedContent wrapper intact.

import { DESTRUCTIVE_TOOLS, MAX_INPUT_CHARS, MAX_TOOL_RESULT_CHARS, MODEL_TOOL_ALLOWLIST, TRUNCATION_MARKER } from './constants.js';

export function clampInput(text) {
  const value = String(text ?? '');
  if (value.length <= MAX_INPUT_CHARS) return { text: value, truncated: false };
  return { text: value.slice(0, MAX_INPUT_CHARS), truncated: true };
}

export const isAllowedTool = (name) => MODEL_TOOL_ALLOWLIST.includes(name);

/** Force the session. Any sessionId the model supplied is overwritten. */
export function injectSession(args, sessionId) {
  return { ...(args ?? {}), sessionId };
}

/**
 * Destructive calls need an explicit yes from the human. A confirm flag the model supplied is
 * discarded: only the human's answer counts.
 */
export function needsConfirmation(name, args) {
  if (DESTRUCTIVE_TOOLS.includes(name)) return true;
  return name === 'import_pins' && args?.mode === 'replace';
}

export function withConfirmation(args, confirmed) {
  const copy = { ...(args ?? {}) };
  delete copy.confirm;
  return confirmed ? { ...copy, confirm: true } : copy;
}

export function createToolBudget(max) {
  let used = 0;
  return {
    take() {
      if (used >= max) return false;
      used += 1;
      return true;
    },
    used: () => used,
    max,
  };
}

function shrinkUntrusted(node, limit) {
  if (Array.isArray(node)) return node.map((item) => shrinkUntrusted(item, limit));
  if (node === null || typeof node !== 'object') return node;
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    if (key === 'untrustedContent' && value && typeof value.text === 'string' && value.text.length > limit) {
      out[key] = { ...value, text: value.text.slice(0, limit) + TRUNCATION_MARKER };
    } else {
      out[key] = shrinkUntrusted(value, limit);
    }
  }
  return out;
}

/**
 * Keep a tool result within MAX_TOOL_RESULT_CHARS. JSON results have their untrustedContent text
 * shortened first, so the notice stays intact. Anything else is hard-cut.
 */
export function truncateResult(text) {
  const value = String(text ?? '');
  if (value.length <= MAX_TOOL_RESULT_CHARS) return value;
  try {
    const parsed = JSON.parse(value);
    let limit = MAX_TOOL_RESULT_CHARS;
    let out = JSON.stringify(shrinkUntrusted(parsed, limit));
    while (out.length > MAX_TOOL_RESULT_CHARS && limit > 0) {
      limit = Math.floor(limit / 2);
      out = JSON.stringify(shrinkUntrusted(parsed, limit));
    }
    if (out.length <= MAX_TOOL_RESULT_CHARS) return out;
  } catch {
    // not JSON: fall through to the hard cut
  }
  return value.slice(0, MAX_TOOL_RESULT_CHARS - TRUNCATION_MARKER.length) + TRUNCATION_MARKER;
}
