import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchPins } from '../src/search.js';
import { fnvHex } from '../src/text.js';

const pin = (pinId, overrides) => ({
  pinId,
  kind: 'pin',
  messageId: null,
  targetHash: fnvHex(pinId),
  role: 'assistant',
  snippet: '',
  textLength: 0,
  ordinal: 0,
  label: null,
  note: null,
  tags: [],
  order: 100,
  createdAt: 1,
  updatedAt: 1,
  repairCount: 0,
  ...overrides,
});

test('T-SRCH-1: keyword hit on label/tag ranks above a weak fuzzy hit', () => {
  const pins = [
    pin('p_weak', { order: 100, snippet: 'authorization' }),
    pin('p_strong', { order: 200, label: 'auth plan', tags: ['auth'], snippet: 'short lived tokens' }),
  ];
  const results = searchPins(pins, 'auth', 10);
  assert.equal(results[0].pin.pinId, 'p_strong');
  assert.ok(results[0].score > results[1].score);
  assert.ok(results[0].matchedOn.includes('label'));
});

test('T-SRCH-1: below-threshold pins are dropped and limit is respected', () => {
  const pins = [
    pin('p_auth1', { label: 'auth one' }),
    pin('p_auth2', { label: 'auth two' }),
    pin('p_unrelated', { snippet: 'quarterly revenue forecast numbers' }),
  ];
  const all = searchPins(pins, 'auth', 10);
  assert.equal(all.some((r) => r.pin.pinId === 'p_unrelated'), false);
  assert.equal(searchPins(pins, 'auth', 1).length, 1);
});
