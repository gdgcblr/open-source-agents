#!/usr/bin/env node

if (process.env.CONVOY_MOCK_EARLY_EXIT === '1') process.exit(17);

const parts = [];
for await (const part of process.stdin) parts.push(part);
const input = Buffer.concat(parts);
if (input.length < 4) process.exit(2);
const length = input.readUInt32LE(0);
if (input.length < length + 4) process.exit(3);
const request = JSON.parse(input.subarray(4, length + 4).toString('utf8'));
const statePath = process.env.CONVOY_MOCK_STATE_FILE;
const state = statePath ? JSON.parse(await (await import('node:fs/promises')).readFile(statePath, 'utf8')) : {};
process.stderr.write('Native messaging host started\n');
if (state.stderr) process.stderr.write(state.stderr);

let response;
switch (request.type) {
  case 'ping': response = { status: 'ok', version: 'mock-1', appRunning: state.running !== false }; break;
  case 'launchApp': state.running = true; response = { success: true }; break;
  case 'getDownloads': response = { success: true, downloads: state.downloads ?? [] }; break;
  case 'downloadRequest': {
    state.downloads ??= [];
    state.nextId ??= 1;
    const payload = request.payload ?? {};
    for (const url of payload.urls ?? []) {
      state.downloads.push({
        id: `created-${state.nextId++}`, filename: payload.filename ?? 'download.bin', url,
        progress: 0, status: 'waiting', speed: 0, totalBytes: 0, downloadedBytes: 0,
      });
    }
    response = { success: true, count: (payload.urls ?? []).length };
    break;
  }
  case 'pauseDownload':
  case 'resumeDownload':
  case 'cancelDownload': {
    const id = request.payload?.id;
    const row = (state.downloads ?? []).find((item) => item.id === id);
    if (!row) response = { success: false, error: 'Download not found' };
    else {
      row.status = request.type.replace('Download', '');
      response = { success: true };
    }
    break;
  }
  default: response = state.failure ?? { success: false, error: `Unknown type: ${request.type}` };
}

if (statePath) await (await import('node:fs/promises')).writeFile(statePath, JSON.stringify(state));
const output = Buffer.from(JSON.stringify(response));
const header = Buffer.alloc(4);
header.writeUInt32LE(output.length);
process.stdout.write(Buffer.concat([header, output]));
