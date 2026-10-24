import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, it } from 'node:test';
import { addDownload, controlDownload, normalizeStatus, verifyDownload } from '../dist/convoy.js';
import { callHost } from '../dist/host.js';

const mockHost = fileURLToPath(new URL('./mock-host.mjs', import.meta.url));
let directory;
let statePath;
let originalHost;
let originalState;
let originalEarlyExit;

async function setState(state) {
  await writeFile(statePath, JSON.stringify(state));
}

describe('Convoy MCP host and operations', () => {
  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), 'convoy-mcp-test-'));
    statePath = join(directory, 'state.json');
    originalHost = process.env.CONVOY_HOST;
    originalState = process.env.CONVOY_MOCK_STATE_FILE;
    originalEarlyExit = process.env.CONVOY_MOCK_EARLY_EXIT;
    process.env.CONVOY_HOST = mockHost;
    process.env.CONVOY_MOCK_STATE_FILE = statePath;
    delete process.env.CONVOY_MOCK_EARLY_EXIT;
    await setState({ running: true, nextId: 1, downloads: [] });
  });

  afterEach(async () => {
    if (originalHost === undefined) delete process.env.CONVOY_HOST;
    else process.env.CONVOY_HOST = originalHost;
    if (originalState === undefined) delete process.env.CONVOY_MOCK_STATE_FILE;
    else process.env.CONVOY_MOCK_STATE_FILE = originalState;
    if (originalEarlyExit === undefined) delete process.env.CONVOY_MOCK_EARLY_EXIT;
    else process.env.CONVOY_MOCK_EARLY_EXIT = originalEarlyExit;
    await rm(directory, { recursive: true, force: true });
  });

  it('frames requests and responses with the host protocol', async () => {
    assert.deepEqual(await callHost({ type: 'ping' }), {
      status: 'ok', version: 'mock-1', appRunning: true,
    });
  });

  it('normalizes Swift associated-value status strings', () => {
    assert.equal(normalizeStatus('urlExpired(referrerURL: https://example.com)'), 'url_expired');
    assert.equal(normalizeStatus('destinationMissing(path: /tmp/file)'), 'destination_missing');
    assert.equal(normalizeStatus('failed(Optional(error))'), 'failed');
  });

  it('reports host stderr alongside a framed failure response', async () => {
    await setState({ stderr: 'Launch Services: kLSNoExecutableErr', failure: { success: false, error: 'Timed out waiting for Convoy to start' } });
    const response = await callHost({ type: 'forcedFailure' });
    assert.equal(response.success, false);
    assert.match(String(response.error), /Timed out waiting for Convoy to start/);
    assert.match(String(response.error), /kLSNoExecutableErr/);
    assert.doesNotMatch(String(response.error), /Native messaging host started/);
  });

  it('rejects if the host exits before accepting stdin without an unhandled EPIPE', async () => {
    process.env.CONVOY_MOCK_EARLY_EXIT = '1';
    await assert.rejects(callHost({ type: 'ping' }), /no response|send request/i);
  });

  it('returns the newly queued task instead of an older task with the same URL', async () => {
    const url = 'https://example.com/archive.zip';
    await setState({ running: true, nextId: 1, downloads: [{
      id: 'old-completed', filename: 'archive.zip', url, progress: 1, status: 'completed',
      speed: 0, totalBytes: 10, downloadedBytes: 10,
    }] });
    const result = await addDownload(url);
    assert.equal(result.id, 'created-1');
    assert.equal(result.state, 'waiting');
  });

  it('keeps the friendly inactive-download error when the host prints its banner', async () => {
    await assert.rejects(controlDownload('pause', 'missing-id'), /Download is not active/);
  });

  it('verifies a completed task using the path returned by Convoy', async () => {
    const contents = 'fixture download bytes';
    const filePath = join(directory, 'fixture.bin');
    await writeFile(filePath, contents);
    const expected = createHash('sha256').update(contents).digest('hex');
    await setState({ running: true, downloads: [{
      id: 'fixture-id', filename: 'fixture.bin', url: 'https://example.com/fixture.bin',
      progress: 1, status: 'completed', speed: 0, totalBytes: contents.length,
      downloadedBytes: contents.length, path: filePath,
    }] });
    const result = await verifyDownload('fixture-id', expected);
    assert.equal(result.matches, true);
    assert.equal(result.actualSha256, expected);
  });
});
