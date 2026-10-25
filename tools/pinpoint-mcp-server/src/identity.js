// Message identity resolution (brief §6.5): id → text hash → fuzzy trigram recovery.
// Pure functions. The caller persists any repair inside store.mutate.

import { AMBIGUITY_MARGIN, FUZZY_MATCH_THRESHOLD, SEARCH_MIN_SCORE } from './constants.js';
import { tokenCoverage, tokenize } from './search.js';
import { normaliseForHash, trigramSimilarity } from './text.js';

const nearest = (items, ordinal) =>
  [...items].sort((a, b) => Math.abs(a.ordinal - ordinal) - Math.abs(b.ordinal - ordinal) || a.ordinal - b.ordinal)[0];

/**
 * Resolve where a pin points now.
 * @returns {{ message: object|null, method: string, repair?: { messageId: string, targetHash: string } }}
 */
export function resolvePinTarget(session, pin) {
  const messages = session.messages;

  if (pin.messageId) {
    const byId = messages.find((m) => m.messageId === pin.messageId);
    if (byId) return { message: byId, method: 'id' };
  }

  const byHash = messages.filter((m) => m.textHash === pin.targetHash);
  if (byHash.length > 0) return { message: nearest(byHash, pin.ordinal), method: 'hash' };

  if (messages.length === 0 && !pin.messageId) return { message: null, method: 'snippet_only' };

  const snippet = normaliseForHash(pin.snippet ?? '');
  if (snippet.length > 0) {
    let best = null;
    for (const message of messages) {
      const prefix = normaliseForHash(message.text).slice(0, snippet.length);
      const score = trigramSimilarity(snippet, prefix);
      if (score < FUZZY_MATCH_THRESHOLD) continue;
      if (
        !best ||
        score > best.score ||
        (score === best.score && Math.abs(message.ordinal - pin.ordinal) < Math.abs(best.message.ordinal - pin.ordinal))
      ) {
        best = { message, score };
      }
    }
    if (best) {
      return {
        message: best.message,
        method: 'fuzzy',
        repair: { messageId: best.message.messageId, targetHash: best.message.textHash },
      };
    }
  }

  return { message: null, method: 'not_found' };
}

const summarise = (message, score) => ({
  messageId: message.messageId,
  ordinal: message.ordinal,
  role: message.role,
  score: Math.round(score * 1000) / 1000,
});

/**
 * Select exactly one message. Selector must contain exactly one of:
 * messageId | ordinal | last ("assistant"|"user"|"any") | textQuery.
 * @returns {{ message } | { error: { code, message, candidates? } }}
 */
export function selectMessage(session, selector) {
  const keys = ['messageId', 'ordinal', 'last', 'textQuery'].filter((k) => selector[k] !== undefined);
  if (keys.length !== 1) {
    return { error: { code: 'INVALID_SELECTOR', message: 'provide exactly one of messageId, ordinal, last, textQuery' } };
  }
  const messages = session.messages;
  const key = keys[0];

  if (key === 'messageId') {
    const message = messages.find((m) => m.messageId === selector.messageId);
    return message ? { message } : { error: { code: 'NOT_FOUND', message: 'no message with that id' } };
  }
  if (key === 'ordinal') {
    const message = messages.find((m) => m.ordinal === selector.ordinal);
    return message ? { message } : { error: { code: 'NOT_FOUND', message: 'no message at that ordinal' } };
  }
  if (key === 'last') {
    const wanted = selector.last;
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (wanted === 'any' || m.role === wanted) return { message: m };
    }
    return { error: { code: 'NOT_FOUND', message: `no ${wanted} message in this session` } };
  }

  const queryTokens = tokenize(selector.textQuery);
  const queryNorm = normaliseForHash(selector.textQuery);
  const scored = messages
    .map((message) => {
      const norm = normaliseForHash(message.text);
      const score = Math.max(trigramSimilarity(queryNorm, norm), tokenCoverage(queryTokens, tokenize(message.text)));
      return { message, score };
    })
    .filter((s) => s.score >= SEARCH_MIN_SCORE)
    .sort((a, b) => b.score - a.score || a.message.ordinal - b.message.ordinal);

  if (scored.length === 0) return { error: { code: 'NOT_FOUND', message: 'no message matches that text' } };
  const [top, second] = scored;
  if (second && top.score - second.score <= AMBIGUITY_MARGIN) {
    return {
      error: {
        code: 'AMBIGUOUS',
        message: 'more than one message matches equally well',
        candidates: [summarise(top.message, top.score), summarise(second.message, second.score)],
      },
    };
  }
  return { message: top.message };
}
