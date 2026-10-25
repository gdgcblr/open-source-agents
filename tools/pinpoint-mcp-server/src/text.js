// Deterministic hashing, normalisation and similarity primitives.
// Ported from ai-pinpoint src/shared/hash.ts (MIT, TeamAnoryx/ai-pinpoint) and adapted to JavaScript.

const FNV_OFFSET_BASIS = 0x811c9dc5;
const FNV_PRIME = 0x01000193;

/** 32-bit FNV-1a over UTF-16 code units. Returns an unsigned 32-bit integer. */
export function fnv1a32(input) {
  let hash = FNV_OFFSET_BASIS;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, FNV_PRIME) >>> 0;
  }
  return hash >>> 0;
}

/** FNV-1a as 8 lowercase hex chars. */
export function fnvHex(input) {
  return fnv1a32(input).toString(16).padStart(8, '0');
}

// Zero-width (U+200B–U+200F), bidi embedding/override (U+202A–U+202E), word joiners, BOM.
const INVISIBLE_MARKS = /[\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]/g;
const PUNCTUATION_RUN = /[\p{P}\p{S}]+/gu;
const WHITESPACE_RUN = /\s+/g;
// C0/C1 control characters except tab (\t, 0x09) and newline (\n, 0x0A).
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u0008\u000B-\u001F\u007F-\u009F]/g;

/**
 * NFC, strip invisible marks, lowercase, punctuation runs to a space, collapse whitespace, trim.
 * Punctuation becomes a space (not removed) so adjacent words never merge.
 */
export function normaliseForHash(text) {
  return String(text)
    .normalize('NFC')
    .replace(INVISIBLE_MARKS, '')
    .toLowerCase()
    .replace(PUNCTUATION_RUN, ' ')
    .replace(WHITESPACE_RUN, ' ')
    .trim();
}

/** Strip control characters except \n and \t (G2). */
export function stripControlChars(text) {
  return String(text).replace(CONTROL_CHARS, '');
}

function trigrams(text) {
  const padded = ` ${text} `;
  const grams = new Set();
  for (let i = 0; i + 3 <= padded.length; i++) {
    grams.add(padded.slice(i, i + 3));
  }
  return grams;
}

/**
 * Jaccard similarity over character trigrams, in [0, 1].
 * If `minSimilarity` is unreachable given the set sizes, returns 0 without intersecting.
 */
export function trigramSimilarity(a, b, minSimilarity = 0) {
  if (a === b) return 1;
  if (a.length === 0 || b.length === 0) return 0;

  const gramsA = trigrams(a);
  const gramsB = trigrams(b);
  const [small, large] = gramsA.size <= gramsB.size ? [gramsA, gramsB] : [gramsB, gramsA];

  // Jaccard upper bound is |small| / |large|.
  if (small.size / large.size < minSimilarity) return 0;

  let intersection = 0;
  for (const gram of small) {
    if (large.has(gram)) intersection++;
  }
  return intersection / (small.size + large.size - intersection);
}

/**
 * Clamp to `max` UTF-16 units without leaving a lone high surrogate at the cut.
 */
export function clampText(text, max) {
  const value = String(text);
  if (value.length <= max) return value;
  let end = max;
  const code = value.charCodeAt(end - 1);
  if (code >= 0xd800 && code <= 0xdbff) end -= 1;
  return value.slice(0, end);
}
