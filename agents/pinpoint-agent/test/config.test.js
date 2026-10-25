import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ConfigError, loadConfig, loadDotEnv, redactSecret } from '../src/config.js';

test('T-AG-10: the default server path resolves to an existing server entry point', () => {
  const config = loadConfig({});
  assert.equal(fs.existsSync(config.serverPath), true, `missing: ${config.serverPath}`);
  assert.equal(config.apiKey, null, 'no key set means mock mode');
  assert.equal(config.maxToolCalls, 6);
});

test('T-AG-10b: bad limits are refused with ConfigError', () => {
  assert.throws(() => loadConfig({ AGENT_MAX_TOOL_CALLS: '0' }), ConfigError);
  assert.throws(() => loadConfig({ AGENT_LOG_LEVEL: 'shout' }), ConfigError);
});

test('redactSecret removes the key wherever it appears', () => {
  const key = ['AI', 'za'].join('') + 'FAKE'.repeat(8) + 'FAK';
  assert.equal(redactSecret(`error with ${key} inside`, key), 'error with [REDACTED:api-key] inside');
  assert.equal(redactSecret('no secret here', null), 'no secret here');
});

test('T-AG-10c: a .env path that cannot be read is a ConfigError, not a crash', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-env-'));
  try {
    const envDir = path.join(dir, '.env');
    fs.mkdirSync(envDir);
    assert.throws(() => loadDotEnv(envDir), ConfigError);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
