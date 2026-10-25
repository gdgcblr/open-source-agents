import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Writable } from 'node:stream';
import { createLogger } from '../src/logger.js';
import { createStore } from '../src/store.js';
import { fnvHex } from '../src/text.js';
import { MAX_MESSAGES_PER_SESSION, MAX_PINS_PER_SESSION, MAX_SESSIONS } from '../src/constants.js';

const realIo = {
  readFileSync: (p) => fs.readFileSync(p, 'utf8'),
  writeFileSync: (p, d) => fs.writeFileSync(p, d, 'utf8'),
  renameSync: (a, b) => fs.renameSync(a, b),
  existsSync: (p) => fs.existsSync(p),
  unlinkSync: (p) => fs.unlinkSync(p),
};
const quietLogger = () => {
  const sink = new Writable({ write: (_c, _e, cb) => cb() });
  return createLogger('error', sink);
};

let dir;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-store-'));
});
afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

const storeFile = () => path.join(dir, 'store.json');
const message = (ordinal, text = `message ${ordinal}`) => ({
  messageId: `m_${ordinal}_abcdef`,
  ordinal,
  role: 'user',
  text,
  textHash: fnvHex(text),
  textLength: text.length,
  redacted: false,
  suspicious: false,
  createdAt: 1,
});
const writeRaw = (doc) => fs.writeFileSync(storeFile(), JSON.stringify(doc));

test('T-STO-1: create and read round-trip survives reload', async () => {
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const created = await store.createSession('Auth redesign chat');
  assert.equal(created.ok, true);
  const reloaded = createStore({ dataDir: dir, logger: quietLogger() });
  reloaded.load();
  const session = reloaded.snapshot().sessions[created.value];
  assert.equal(session.title, 'Auth redesign chat');
});

test('T-STO-2: failed rename mid-mutate leaves previous store.json intact', async () => {
  const good = createStore({ dataDir: dir, logger: quietLogger(), io: realIo });
  good.load();
  await good.createSession('keep me');
  const before = fs.readFileSync(storeFile(), 'utf8');

  const broken = createStore({
    dataDir: dir,
    logger: quietLogger(),
    io: { ...realIo, renameSync: () => { throw Object.assign(new Error('boom'), { code: 'EIO' }); } },
  });
  broken.load();
  const result = await broken.createSession('never lands');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'STORAGE_ERROR');
  assert.equal(fs.readFileSync(storeFile(), 'utf8'), before);
  const titles = Object.values(broken.snapshot().sessions).map((s) => s.title);
  assert.deepEqual(titles, ['keep me']);
});

test('T-STO-3: corrupt JSON is renamed to store.corrupt-*.json, store starts empty, file kept', () => {
  fs.writeFileSync(storeFile(), '{not json');
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const files = fs.readdirSync(dir);
  assert.ok(files.some((f) => /^store\.corrupt-.*\.json$/.test(f)));
  assert.equal(Object.keys(store.snapshot().sessions).length, 0);
  assert.equal(store.health().lastCorruptionEvent.reason, 'unparseable JSON');
});

test('T-STO-4: invalid records go to quarantine.json, valid ones are kept', () => {
  const good = {
    sessionId: 's_good_aaaaaa',
    title: 'good',
    createdAt: 1,
    updatedAt: 1,
    messages: [message(0), { messageId: 'bad' }],
    pins: [],
  };
  const bad = { sessionId: 'nope', createdAt: 1, updatedAt: 1 };
  writeRaw({ kind: 'pinpoint-mcp-store', schema: 1, sessions: { [good.sessionId]: good, nope: bad } });
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const session = store.snapshot().sessions[good.sessionId];
  assert.equal(session.messages.length, 1);
  const quarantine = JSON.parse(fs.readFileSync(path.join(dir, 'quarantine.json'), 'utf8'));
  assert.ok(quarantine.length >= 2);
  assert.equal(store.health().quarantined >= 2, true);
});

test('T-STO-5: session, message and pin caps return typed errors', async () => {
  const sessions = {};
  for (let i = 0; i < MAX_SESSIONS; i++) {
    const sessionId = `s_cap_${String(i).padStart(4, '0')}`;
    sessions[sessionId] = { sessionId, title: null, createdAt: 1, updatedAt: 1, messages: [], pins: [] };
  }
  writeRaw({ kind: 'pinpoint-mcp-store', schema: 1, sessions });
  const full = createStore({ dataDir: dir, logger: quietLogger() });
  full.load();
  assert.equal((await full.createSession('one too many')).error.code, 'LIMIT_SESSIONS');

  const bigMessages = Array.from({ length: MAX_MESSAGES_PER_SESSION }, (_, i) => message(i));
  const bigPins = Array.from({ length: MAX_PINS_PER_SESSION }, (_, i) => ({
    pinId: `p_cap_${i}_aaaaaa`,
    kind: 'pin',
    messageId: null,
    targetHash: fnvHex('x'),
    role: 'user',
    snippet: 'x',
    textLength: 1,
    ordinal: 0,
    label: null,
    note: null,
    tags: [],
    order: i * 100,
    createdAt: 1,
    updatedAt: 1,
    repairCount: 0,
  }));
  writeRaw({
    kind: 'pinpoint-mcp-store',
    schema: 1,
    sessions: { s_big_aaaaaa: { sessionId: 's_big_aaaaaa', title: null, createdAt: 1, updatedAt: 1, messages: bigMessages, pins: bigPins } },
  });
  const capped = createStore({ dataDir: dir, logger: quietLogger() });
  capped.load();
  assert.equal((await capped.appendMessage('s_big_aaaaaa', {})).error.code, 'LIMIT_MESSAGES');
  assert.equal((await capped.addPin('s_big_aaaaaa', bigPins[0])).error.code, 'LIMIT_PINS');
});

test('T-STO-6: 50 parallel appends serialise with no lost update', async () => {
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const { value: sessionId } = await store.createSession('parallel');
  const results = await Promise.all(Array.from({ length: 50 }, (_, i) => store.appendMessage(sessionId, message(i, `t${i}`))));
  assert.ok(results.every((r) => r.ok));
  const reloaded = createStore({ dataDir: dir, logger: quietLogger() });
  reloaded.load();
  const messages = reloaded.snapshot().sessions[sessionId].messages;
  assert.equal(messages.length, 50);
  assert.equal(new Set(messages.map((m) => m.ordinal)).size, 50);
});

test('T-STO-7: null and empty inputs are handled without throwing', async () => {
  const store = createStore({ dataDir: dir, logger: quietLogger() });
  store.load();
  const nullTitle = await store.createSession(null);
  assert.equal(nullTitle.ok, true);
  assert.equal(store.snapshot().sessions[nullTitle.value].title, null);
  const emptyTitle = await store.createSession('');
  assert.equal(emptyTitle.ok, true);
  assert.equal(store.snapshot().sessions[emptyTitle.value].title, '');

  const sessionId = nullTitle.value;
  const emptyText = await store.appendMessage(sessionId, {
    role: 'user',
    text: '',
    textHash: fnvHex(''),
    textLength: 0,
    redacted: false,
    suspicious: false,
  });
  assert.equal(emptyText.ok, true);
  assert.equal(store.snapshot().sessions[sessionId].messages[0].text, '');

  const nullText = await store.appendMessage(sessionId, {
    role: 'user',
    text: null,
    textHash: fnvHex(''),
    textLength: 0,
    redacted: false,
    suspicious: false,
  });
  assert.equal(nullText.ok, false);
  assert.equal(nullText.error.code, 'STORAGE_INVALID');
});

test('load: read failure (EACCES) throws STORAGE_ERROR and leaves store.json in place', async () => {
  const good = createStore({ dataDir: dir, logger: quietLogger(), io: realIo });
  good.load();
  await good.createSession('healthy');
  const before = fs.readFileSync(storeFile(), 'utf8');

  const denied = createStore({
    dataDir: dir,
    logger: quietLogger(),
    io: { ...realIo, readFileSync: () => { throw Object.assign(new Error('denied'), { code: 'EACCES' }); } },
  });
  assert.throws(() => denied.load(), (err) => err.code === 'STORAGE_ERROR');
  assert.equal(denied.health().lastCorruptionEvent, null);
  assert.equal(fs.readFileSync(storeFile(), 'utf8'), before);
  assert.equal(fs.readdirSync(dir).some((f) => /^store\.corrupt-/.test(f)), false);
});

test('T-STO-8: LOCK_TIMEOUT keeps queue order; no mutation overtakes the slow holder', async () => {
  const store = createStore({ dataDir: dir, logger: quietLogger(), lockTimeoutMs: 50 });
  const order = [];
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const slow = store.mutate(async () => {
    order.push('slow-start');
    await sleep(200);
    order.push('slow-end');
  });
  const timedOut = await store.mutate(() => {
    order.push('timed-out');
  });
  const probe = await store.mutate(() => {
    order.push('probe');
  });
  await slow;
  const final = await store.mutate(() => {
    order.push('final');
  });

  assert.equal(timedOut.error.code, 'LOCK_TIMEOUT');
  assert.equal(probe.error.code, 'LOCK_TIMEOUT');
  assert.equal(final.ok, true);
  assert.deepEqual(order, ['slow-start', 'slow-end', 'final']);
});
