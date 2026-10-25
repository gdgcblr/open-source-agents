// Test harness: a real MCP client talking to createServer over the SDK's in-memory transport.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Writable } from 'node:stream';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { createAudit } from '../src/audit.js';
import { createLogger } from '../src/logger.js';
import { createServer } from '../src/server.js';
import { createStore } from '../src/store.js';

export const quietLogger = () => createLogger('error', new Writable({ write: (_c, _e, cb) => cb() }));

/** Build a fake key at runtime so no key-shaped literal lives in the source (secret scanner). */
export const fakeOpenAiKey = () => ['s', 'k-'].join('') + 'FAKE'.repeat(6);

export async function setup({ redact = true, audit = true } = {}) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-tools-'));
  const logger = quietLogger();
  const config = Object.freeze({ dataDir, logLevel: 'error', audit, redact, rateLimitPerMin: 120 });
  const store = createStore({ dataDir, logger });
  store.load();
  const auditLog = createAudit({ dataDir, enabled: audit });
  const server = createServer({ store, audit: auditLog, config, logger });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  const client = new Client({ name: 'pinpoint-test', version: '0.0.0' });
  await client.connect(clientTransport);

  /** Call a tool and parse the JSON envelope. Returns { isError, body }. */
  async function call(name, args = {}) {
    const result = await client.callTool({ name, arguments: args });
    return { isError: result.isError === true, body: JSON.parse(result.content[0].text), raw: result };
  }

  async function close() {
    await client.close();
    await server.close();
    fs.rmSync(dataDir, { recursive: true, force: true });
  }

  return { client, call, dataDir, config, store, server, close };
}
