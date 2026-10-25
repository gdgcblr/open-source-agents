import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MAX_MESSAGE_CHARS } from '../src/constants.js';
import { validateMessage, validatePin, validateSession, validateStore } from '../src/schema.js';
import { fnvHex } from '../src/text.js';

const GARBAGE = [null, undefined, [], 0, -1, 3.5, 'x', true, {}, { deep: { deeper: [1, { x: null }] } }, [[[]]], Symbol.for('x')];

test('T-SCH-1: validators never throw on garbage input', () => {
  for (const value of GARBAGE) {
    assert.doesNotThrow(() => validateMessage(value));
    assert.doesNotThrow(() => validatePin(value));
    assert.doesNotThrow(() => validateSession(value));
    assert.doesNotThrow(() => validateStore(value));
    assert.equal(validateStore(value).ok, false);
  }
  assert.equal(validateSession({ sessionId: 's_x', createdAt: 1, updatedAt: 1, messages: 'no' }).ok, false);
});

test('T-SCH-1: unknown keys are stripped and text is clamped', () => {
  const result = validateMessage({
    messageId: 'm_1',
    ordinal: 0,
    role: 'user',
    text: 'a'.repeat(MAX_MESSAGE_CHARS + 500) + '\u0007',
    textHash: fnvHex('x'),
    textLength: 5,
    createdAt: 1,
    evil: 'extra',
  });
  assert.equal(result.ok, true);
  assert.equal('evil' in result.value, false);
  assert.equal(result.value.text.length, MAX_MESSAGE_CHARS);
});

test('T-SCH-1: bookmark without label is rejected; bad role rejected', () => {
  const base = {
    pinId: 'p_1',
    kind: 'bookmark',
    messageId: null,
    targetHash: fnvHex('x'),
    role: 'user',
    snippet: 'x',
    textLength: 1,
    ordinal: 0,
    order: 100,
    createdAt: 1,
    updatedAt: 1,
    repairCount: 0,
  };
  assert.equal(validatePin(base).ok, false);
  assert.equal(validatePin({ ...base, kind: 'pin', role: 'admin' }).ok, false);
  assert.equal(validatePin({ ...base, kind: 'pin' }).ok, true);
});

test('T-SCH-1: text exactly at MAX_MESSAGE_CHARS is kept whole; one over is clamped', () => {
  const base = {
    messageId: 'm_1',
    ordinal: 0,
    role: 'user',
    textHash: fnvHex('x'),
    textLength: 1,
    createdAt: 1,
  };
  const atLimit = validateMessage({ ...base, text: 'a'.repeat(MAX_MESSAGE_CHARS) });
  assert.equal(atLimit.ok, true);
  assert.equal(atLimit.value.text.length, MAX_MESSAGE_CHARS);
  const overLimit = validateMessage({ ...base, text: 'a'.repeat(MAX_MESSAGE_CHARS + 1) });
  assert.equal(overLimit.value.text.length, MAX_MESSAGE_CHARS);
});

test('T-SCH-1: empty-string message text is accepted as-is', () => {
  const result = validateMessage({
    messageId: 'm_1',
    ordinal: 0,
    role: 'user',
    text: '',
    textHash: fnvHex(''),
    textLength: 0,
    createdAt: 1,
  });
  assert.equal(result.ok, true);
  assert.equal(result.value.text, '');
});
