// Pin search: keyword token coverage on label/tags/note/snippet, or fuzzy trigram similarity.
// Scoring rules: brief §6.6 tool 6 (search_pins).

import { SEARCH_MIN_SCORE } from './constants.js';
import { normaliseForHash, trigramSimilarity } from './text.js';

const FIELD_WEIGHTS = Object.freeze({ label: 1, tags: 1, note: 0.9, snippet: 0.8 });

/** Normalised word tokens. */
export function tokenize(text) {
  const norm = normaliseForHash(text);
  return norm.length === 0 ? [] : norm.split(' ');
}

/** Fraction of query tokens present in the text's token set. 0 when the query is empty. */
export function tokenCoverage(queryTokens, textTokens) {
  if (queryTokens.length === 0) return 0;
  const present = new Set(textTokens);
  let hits = 0;
  for (const token of queryTokens) {
    if (present.has(token)) hits++;
  }
  return hits / queryTokens.length;
}

/**
 * Score one pin against a query. Returns { score, matchedOn }.
 * score = max(weighted keyword coverage per field, trigram similarity against the whole pin).
 */
export function scorePin(pin, query) {
  const queryTokens = tokenize(query);
  const queryNorm = normaliseForHash(query);
  const fields = {
    label: pin.label ?? '',
    tags: (pin.tags ?? []).join(' '),
    note: pin.note ?? '',
    snippet: pin.snippet ?? '',
  };

  let keyword = 0;
  const matchedOn = [];
  for (const [field, text] of Object.entries(fields)) {
    const coverage = tokenCoverage(queryTokens, tokenize(text)) * FIELD_WEIGHTS[field];
    if (coverage > 0) matchedOn.push(field);
    keyword = Math.max(keyword, coverage);
  }

  const haystack = Object.values(fields).join(' ');
  const fuzzy = trigramSimilarity(queryNorm, normaliseForHash(haystack));
  const score = Math.max(keyword, fuzzy);
  if (fuzzy > 0 && fuzzy >= keyword) matchedOn.push('fuzzy');
  return { score: Math.round(score * 1000) / 1000, matchedOn };
}

/**
 * Rank pins for a query. Drops scores below SEARCH_MIN_SCORE, sorts by score desc then
 * by stored order, and applies the limit.
 */
export function searchPins(pins, query, limit) {
  const ranked = [];
  for (const pin of pins) {
    const { score, matchedOn } = scorePin(pin, query);
    if (score >= SEARCH_MIN_SCORE) ranked.push({ pin, score, matchedOn });
  }
  ranked.sort((a, b) => b.score - a.score || a.pin.order - b.pin.order);
  return ranked.slice(0, limit);
}
