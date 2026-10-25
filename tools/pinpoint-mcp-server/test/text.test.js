import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clampText, fnv1a32, normaliseForHash, trigramSimilarity } from '../src/text.js';

test('T-TXT-1: fnv1a32 matches known vectors', () => {
  assert.equal(fnv1a32(''), 0x811c9dc5);
  assert.equal(fnv1a32('a'), 0xe40c292c);
});

test('T-TXT-2: normaliseForHash strips invisible marks, folds punctuation and case', () => {
  assert.equal(normaliseForHash('Hello​, ‮WORLD!!  '), 'hello world');
  assert.equal(normaliseForHash('Café-ok'), 'café ok');
  assert.equal(normaliseForHash('Café'), normaliseForHash('Café'));
});

test('T-TXT-3: trigramSimilarity is 1 for equal, 0 for empty, symmetric, early-exits below bound', () => {
  assert.equal(trigramSimilarity('abc', 'abc'), 1);
  assert.equal(trigramSimilarity('', 'x'), 0);
  assert.equal(trigramSimilarity('auth plan', 'plan auth'), trigramSimilarity('plan auth', 'auth plan'));
  assert.equal(trigramSimilarity('a', 'abcdefghijklmnop', 0.9), 0);
});

test('T-TXT-4: clampText never leaves a lone high surrogate', () => {
  const out = clampText('ab\u{1F600}\u{1F600}', 3);
  assert.equal(out, 'ab');
  assert.doesNotMatch(out, /[\uD800-\uDBFF]$/);
  assert.equal(clampText('short', 10), 'short');
});
