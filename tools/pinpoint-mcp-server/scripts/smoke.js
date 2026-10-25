// End-to-end smoke: spawn src/index.js over real stdio with a temp data dir, call all 13 tools
// in one realistic flow, assert every reply is ok, print a transcript, clean up. Exit 1 on failure.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport, getDefaultEnvironment } from '@modelcontextprotocol/sdk/client/stdio.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SERVER_ENTRY = path.resolve(HERE, '..', 'src', 'index.js');

export async function runSmoke(options = {}) {
  try {
    return await runSmokeFlow(options);
  } catch (error) {
    const log = options.log ?? ((line) => process.stdout.write(`${line}\n`));
    log(`FAIL  smoke aborted: ${error.code ?? error.message}`);
    return 1;
  }
}

async function runSmokeFlow({ log = (line) => process.stdout.write(`${line}\n`) } = {}) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-smoke-'));
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [SERVER_ENTRY],
    env: { ...getDefaultEnvironment(), PINPOINT_DATA_DIR: dataDir },
    stderr: 'ignore',
  });
  const client = new Client({ name: 'pinpoint-smoke', version: '0.0.0' });
  const called = new Set();
  let failures = 0;

  async function call(name, args = {}) {
    const result = await client.callTool({ name, arguments: args });
    const body = JSON.parse(result.content[0].text);
    called.add(name);
    const ok = result.isError !== true && body.ok === true;
    if (!ok) failures += 1;
    log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${JSON.stringify(args).slice(0, 80)}  ->  ${summary(body)}`);
    return body;
  }

  try {
    await client.connect(transport);
    const { sessionId } = await call('start_session', { title: 'smoke' });
    await call('record_message', { sessionId, role: 'user', text: 'Explain JWT refresh tokens' });
    await call('record_message', { sessionId, role: 'assistant', text: 'Refresh tokens rotate on every use.' });
    await call('record_message', { sessionId, role: 'assistant', text: 'Keep the old token family revoked on reuse.' });
    const pinned = await call('pin_message', { sessionId, last: 'assistant', label: 'rotation' });
    await call('bookmark_message', { sessionId, ordinal: 0, label: 'jwt-basics' });
    await call('list_pins', { sessionId });
    await call('search_pins', { sessionId, query: 'rotation' });
    await call('navigate_to_pin', { pin: pinned.pin.pinId, contextBefore: 1, contextAfter: 1 });
    await call('update_pin', { pinId: pinned.pin.pinId, label: 'refresh-rotation', tags: ['auth'] });
    const exported = await call('export_pins', { sessionId, fileName: 'smoke-export' });
    fs.mkdirSync(path.join(dataDir, 'imports'), { recursive: true });
    fs.copyFileSync(exported.path, path.join(dataDir, 'imports', 'smoke-export.json'));
    await call('import_pins', { fileName: 'smoke-export', mode: 'merge' });
    await call('unpin', { pinId: pinned.pin.pinId, confirm: true });
    await call('list_sessions');
    await call('health');
  } finally {
    await client.close().catch(() => {});
    fs.rmSync(dataDir, { recursive: true, force: true });
  }

  const missing = 13 - called.size;
  if (missing !== 0) {
    log(`FAIL  tool coverage: ${called.size}/13 tools called`);
    failures += 1;
  }
  log(failures === 0 ? `smoke OK: ${called.size}/13 tools, all replies ok` : `smoke FAILED: ${failures} failure(s)`);
  return failures;
}

function summary(body) {
  const { ok, ...rest } = body;
  return ok ? Object.keys(rest).join(',') || 'ok' : `${body.error?.code}`;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const failures = await runSmoke();
  process.exit(failures === 0 ? 0 : 1);
}
