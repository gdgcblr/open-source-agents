import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { MAX_IMPORT_BYTES } from '../src/constants.js';
import { setup } from './helpers.js';

async function seed(call) {
  const { sessionId } = (await call('start_session', { title: 'seeded' })).body;
  await call('record_message', { sessionId, role: 'user', text: 'Explain JWT refresh tokens' });
  await call('record_message', { sessionId, role: 'assistant', text: 'Refresh tokens rotate on every use.' });
  await call('pin_message', { sessionId, last: 'assistant', label: 'rotation' });
  await call('bookmark_message', { sessionId, ordinal: 0, label: 'jwt-basics' });
  return sessionId;
}

const importsDir = (dataDir) => path.join(dataDir, 'imports');

test('T-TRF-1: export then import on a fresh store round-trips sessions, messages and pins', async () => {
  const source = await setup();
  const target = await setup();
  try {
    await seed(source.call);
    const exported = await source.call('export_pins', { fileName: 'pins-roundtrip' });
    assert.equal(exported.isError, false);
    assert.deepEqual(exported.body.counts, { sessions: 1, messages: 2, pins: 2 });

    fs.mkdirSync(importsDir(target.dataDir), { recursive: true });
    fs.copyFileSync(exported.body.path, path.join(importsDir(target.dataDir), 'pins-roundtrip.json'));

    const imported = await target.call('import_pins', { fileName: 'pins-roundtrip' });
    assert.equal(imported.isError, false);
    assert.equal(imported.body.sessionsAdded, 1);
    assert.equal(imported.body.messagesAdded, 2);
    assert.equal(imported.body.pinsAdded, 2);

    const counts = (await target.call('health')).body.counts;
    assert.deepEqual(counts, { sessions: 1, messages: 2, pins: 2 });

    const again = await target.call('import_pins', { fileName: 'pins-roundtrip' });
    assert.equal(again.body.pinsAdded, 0, 'a second merge adds nothing');
    assert.equal(again.body.messagesAdded, 0);
  } finally {
    await source.close();
    await target.close();
  }
});

test('T-TRF-3: malformed, oversized and wrong-kind bundles are refused; bad records are quarantined', async () => {
  const env = await setup();
  try {
    const dir = importsDir(env.dataDir);
    fs.mkdirSync(dir, { recursive: true });

    fs.writeFileSync(path.join(dir, 'broken.json'), '{not json');
    assert.equal((await env.call('import_pins', { fileName: 'broken' })).body.error.code, 'IMPORT_INVALID');

    fs.writeFileSync(path.join(dir, 'wrong-kind.json'), JSON.stringify({ kind: 'something-else', schema: 1, sessions: [] }));
    assert.equal((await env.call('import_pins', { fileName: 'wrong-kind' })).body.error.code, 'IMPORT_INVALID');

    fs.writeFileSync(path.join(dir, 'huge.json'), 'x'.repeat(MAX_IMPORT_BYTES + 1));
    assert.equal((await env.call('import_pins', { fileName: 'huge' })).body.error.code, 'IMPORT_INVALID');

    const mixed = {
      kind: 'pinpoint-mcp-export',
      schema: 1,
      sessions: [
        { sessionId: 's_good_abc', title: null, createdAt: 1, updatedAt: 1, messages: [], pins: [] },
        { sessionId: 'not-a-session', createdAt: 1, updatedAt: 1 },
      ],
    };
    fs.writeFileSync(path.join(dir, 'mixed.json'), JSON.stringify(mixed));
    const result = await env.call('import_pins', { fileName: 'mixed' });
    assert.equal(result.isError, false);
    assert.equal(result.body.sessionsAdded, 1);
    assert.equal(result.body.quarantined, 1);
    const quarantine = JSON.parse(fs.readFileSync(path.join(env.dataDir, 'quarantine.json'), 'utf8'));
    assert.equal(quarantine.length, 1);
    assert.equal(quarantine[0].record.sessionId, 'not-a-session', 'the invalid record is kept, not dropped');
  } finally {
    await env.close();
  }
});

test('T-TRF-4: replace without confirm is refused; with confirm it backs up then replaces', async () => {
  const source = await setup();
  const target = await setup();
  try {
    await seed(source.call);
    const exported = await source.call('export_pins', { fileName: 'replace-source' });
    fs.mkdirSync(importsDir(target.dataDir), { recursive: true });
    fs.copyFileSync(exported.body.path, path.join(importsDir(target.dataDir), 'replace-source.json'));

    await target.call('start_session', { title: 'will be replaced' });
    const refused = await target.call('import_pins', { fileName: 'replace-source', mode: 'replace' });
    assert.equal(refused.body.error.code, 'CONFIRMATION_REQUIRED');
    assert.equal((await target.call('health')).body.counts.sessions, 1, 'nothing changed on refusal');

    const replaced = await target.call('import_pins', { fileName: 'replace-source', mode: 'replace', confirm: true });
    assert.equal(replaced.isError, false);
    assert.ok(replaced.body.backup, 'a backup of the previous store is written');
    assert.equal(fs.existsSync(replaced.body.backup), true);
    const backup = JSON.parse(fs.readFileSync(replaced.body.backup, 'utf8'));
    assert.equal(backup.sessions.length, 1, 'the backup holds the data that was replaced');
    assert.deepEqual((await target.call('health')).body.counts, { sessions: 1, messages: 2, pins: 2 });
  } finally {
    await source.close();
    await target.close();
  }
});

test('T-TRF-5: unreadable import (a directory with a bundle name) is STORAGE_ERROR, not a crash', async () => {
  const env = await setup();
  try {
    fs.mkdirSync(path.join(env.dataDir, 'imports', 'as-dir.json'), { recursive: true });
    const result = await env.call('import_pins', { fileName: 'as-dir' });
    assert.equal(result.isError, true);
    assert.equal(result.body.error.code, 'STORAGE_ERROR');
  } finally {
    await env.close();
  }
});
