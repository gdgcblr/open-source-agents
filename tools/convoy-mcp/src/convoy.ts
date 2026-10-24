import { createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import { callHost, type HostMessage } from './host.js';

export type DownloadStatus = 'waiting' | 'starting' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled' | 'url_expired' | 'destination_missing' | 'other';
export type Download = {
  id: string; filename: string; url: string; progress: number; status: DownloadStatus;
  speed: number; totalBytes: number; downloadedBytes: number; path?: string;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
function requireSuccess(reply: HostMessage, action: string): void {
  if (reply.success !== true) throw new Error(String(reply.error ?? `${action} failed`));
}

export function normalizeStatus(raw: unknown): DownloadStatus {
  const value = String(raw ?? '').toLowerCase();
  if (value.includes('urlexpired') || value.includes('url_expired')) return 'url_expired';
  if (value.includes('destinationmissing') || value.includes('destination_missing')) return 'destination_missing';
  for (const status of ['waiting', 'starting', 'downloading', 'paused', 'completed', 'failed', 'cancelled'] as const) {
    if (value.startsWith(status)) return status;
  }
  return 'other';
}

export async function status(launch = false): Promise<{ version: string; appRunning: boolean }> {
  const ping = await callHost({ type: 'ping' });
  if (launch && ping.appRunning !== true) {
    requireSuccess(await callHost({ type: 'launchApp' }, 12_000), 'Launching Convoy');
    const next = await callHost({ type: 'ping' });
    return { version: String(next.version ?? 'unknown'), appRunning: next.appRunning === true };
  }
  return { version: String(ping.version ?? 'unknown'), appRunning: ping.appRunning === true };
}

export async function listDownloads(): Promise<Download[]> {
  const app = await status();
  if (!app.appRunning) throw new Error('Convoy is not running. Call convoy_status with launch=true, then retry.');
  const reply = await callHost({ type: 'getDownloads' });
  requireSuccess(reply, 'Listing downloads');
  if (!Array.isArray(reply.downloads)) throw new Error('Convoy returned an invalid downloads list');
  return reply.downloads.map((row: Record<string, unknown>) => ({
    id: String(row.id ?? ''), filename: String(row.filename ?? ''), url: String(row.url ?? ''),
    progress: Number(row.progress ?? 0), status: normalizeStatus(row.status), speed: Number(row.speed ?? 0),
    totalBytes: Number(row.totalBytes ?? 0), downloadedBytes: Number(row.downloadedBytes ?? 0),
    ...(typeof row.path === 'string' ? { path: row.path } : {}),
  }));
}

export async function addDownload(url: string, filename?: string, segmentCount?: number): Promise<{ id?: string; state: string; filename?: string }> {
  let parsed: URL;
  try { parsed = new URL(url); } catch { throw new Error('url must be a valid http or https URL'); }
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Only http and https download URLs are supported');
  const before = await status();
  if (!before.appRunning) {
    requireSuccess(await callHost({ type: 'launchApp' }, 12_000), 'Launching Convoy');
  }
  const existingIds = new Set((await listDownloads()).map((download) => download.id));
  const payload: Record<string, unknown> = { type: 'downloadRequest', payload: { urls: [url] } };
  const inner = payload.payload as Record<string, unknown>;
  if (filename) inner.filename = filename;
  if (segmentCount !== undefined) inner.segmentCount = segmentCount;
  let reply = await callHost(payload);
  if (reply.success !== true && String(reply.error).includes('Convoy app not running')) {
    requireSuccess(await callHost({ type: 'launchApp' }, 12_000), 'Launching Convoy');
    reply = await callHost(payload);
  }
  requireSuccess(reply, 'Queueing download');
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const found = (await listDownloads()).find((download) => download.url === url && !existingIds.has(download.id));
    if (found) return { id: found.id, state: found.status, filename: found.filename };
    await sleep(500);
  }
  return { state: 'queued, but no matching task appeared; a duplicate conflict may be waiting for user input' };
}

export async function controlDownload(action: 'pause' | 'resume' | 'cancel', id: string): Promise<void> {
  const type = `${action}Download`;
  const reply = await callHost({ type, payload: { id } });
  if (reply.success !== true) {
    if (String(reply.error ?? '').startsWith('Download not found')) throw new Error('Download is not active (it may be finished or the ID may be unknown)');
    throw new Error(String(reply.error ?? `${action} failed`));
  }
}

export async function verifyDownload(id: string, expected: string): Promise<{ matches: boolean; expectedSha256: string; actualSha256: string; filename: string }> {
  if (!/^[a-f0-9]{64}$/i.test(expected)) throw new Error('expected_sha256 must contain exactly 64 hexadecimal characters');
  const download = (await listDownloads()).find((row) => row.id === id);
  if (!download) throw new Error('Download ID was not found');
  if (download.status !== 'completed') throw new Error(`Download is ${download.status}; only completed downloads can be verified`);
  if (!download.path) throw new Error('This Convoy build does not expose download paths; install a build with getDownloads path support');
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(download.path)) hash.update(chunk);
  const actualSha256 = hash.digest('hex');
  return { matches: actualSha256.toLowerCase() === expected.toLowerCase(), expectedSha256: expected.toLowerCase(), actualSha256, filename: download.filename };
}
