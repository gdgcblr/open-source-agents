import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { loadConfig, ConfigError } from '../src/config.js';

test('config: data dir under an existing file throws ConfigError', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pinpoint-cfg-'));
  try {
    const blocker = path.join(root, 'not-a-dir');
    fs.writeFileSync(blocker, 'x');
    const target = path.join(blocker, 'child');
    assert.throws(() => loadConfig({ PINPOINT_DATA_DIR: target }), (err) => {
      assert.ok(err instanceof ConfigError);
      assert.match(err.message, /Cannot create data directory/);
      return true;
    });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
