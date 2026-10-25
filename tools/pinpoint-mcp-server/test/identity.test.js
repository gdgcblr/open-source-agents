import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Writable } from 'node:stream';
import { createLogger } from '../src/logger.js';
import { createStore } from '../src/store.js';
import { resolvePinTarget, selectMessage } from '../src/identity.js';
import { fnvHex } from '../src/text.js';

const quietLogger = () => createLogger('error', new Writable({ write: (_c, _e, cb) => cb() }));
const msg = (ordinal, text, role = 'user', id = `m_${ordinal}_aaaaaa`) => ({
  messageId: id,
  ordinal,
  role,
  text,
  textHash: fnvHex(text.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim()),
  textLength: text.length,
  redacted: false,
  suspicious: false,
  createdAt: 1,
});
const pinFor = (overrides) => ({
  pinId: 'p_1_aaaaaa',
  kind: 'pin',
  messageId: null,
  targetHash: fnvHex('nothing'),
  role: 'user',
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

let dir;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-id-'));
});
afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

test('T-ID-1: resolution by messageId returns method id', () => {
  const session = { messages: [msg(0, 'first'), msg(1, 'second', 'assistant', 'm_target_zz')] };
  const result = resolvePinTarget(session, pinFor({ messageId: 'm_target_zz', ordinal: 1 }));
  assert.equal(result.method, 'id');
  assert.equal(result.message.ordinal, 1);
});

test('T-ID-2: resolution by hash when id missing; nearest ordinal wins on duplicates', () => {
  const session = {
    messages: [msg(0, 'same text'), msg(5, 'other'), msg(9, 'same text')],
  };
  const hash = session.messages[0].textHash;
  const result = resolvePinTarget(session, pinFor({ messageId: 'm_gone_zzzzzz', targetHash: hash, ordinal: 8 }));
  assert.equal(result.method, 'hash');
  assert.equal(result.message.ordinal, 9);
});

test('T-ID-3: fuzzy recovery after a small edit; repair is reported and repairCount increments in store', async () => {
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const { value: sessionId } = await store.createSession('edit test');
  const edited = msg(0, 'The auth plan is to use short-lived tokens, plus refresh rotation.', 'assistant', 'm_edit_aaaaaa');
  await store.appendMessage(sessionId, edited);
  const pin = pinFor({
    pinId: 'p_fz_aaaaaa',
    messageId: 'm_old_aaaaaa',
    snippet: 'The auth plan is to use short lived tokens',
    targetHash: fnvHex('stale'),
  });
  await store.addPin(sessionId, pin);

  const outcome = await store.mutate((draft) => {
    const session = draft.sessions[sessionId];
    const current = session.pins.find((p) => p.pinId === pin.pinId);
    const result = resolvePinTarget(session, current);
    assert.equal(result.method, 'fuzzy');
    assert.equal(result.repair.messageId, 'm_edit_aaaaaa');
    Object.assign(current, result.repair);
    current.repairCount += 1;
    return result.method;
  });
  assert.equal(outcome.ok, true);
  const repaired = store.snapshot().sessions[sessionId].pins[0];
  assert.equal(repaired.repairCount, 1);
  assert.equal(repaired.messageId, 'm_edit_aaaaaa');
});

test('T-ID-4: not found returns not_found and leaves the pin in place', () => {
  const session = { messages: [msg(0, 'completely unrelated cooking recipe text')] };
  const pin = pinFor({ snippet: 'quarterly revenue forecast numbers', targetHash: fnvHex('zzz') });
  const result = resolvePinTarget(session, pin);
  assert.equal(result.method, 'not_found');
  assert.equal(result.message, null);
  assert.equal(pin.pinId, 'p_1_aaaaaa');
});

test('T-ID-5: selector exactly-one rule, last roles, and textQuery ambiguity', () => {
  const session = {
    messages: [
      msg(0, 'deploy the staging cluster now', 'user'),
      msg(1, 'ok, deploying', 'assistant'),
      msg(2, 'deploy the staging cluster now', 'assistant'),
    ],
  };
  assert.equal(selectMessage(session, {}).error.code, 'INVALID_SELECTOR');
  assert.equal(selectMessage(session, { ordinal: 0, last: 'user' }).error.code, 'INVALID_SELECTOR');
  assert.equal(selectMessage(session, { last: 'assistant' }).message.ordinal, 2);
  assert.equal(selectMessage(session, { last: 'user' }).message.ordinal, 0);
  assert.equal(selectMessage(session, { ordinal: 1 }).message.role, 'assistant');
  const ambiguous = selectMessage(session, { textQuery: 'deploy the staging cluster now' });
  assert.equal(ambiguous.error.code, 'AMBIGUOUS');
  assert.equal(ambiguous.error.candidates.length, 2);
});
