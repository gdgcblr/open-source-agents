#!/usr/bin/env node

import { callHost } from '../dist/host.js';

const type = process.argv.includes('--launch') ? 'launchApp' : 'ping';

try {
  const payload = await callHost({ type }, type === 'launchApp' ? 12_000 : 15_000);
  console.log(JSON.stringify(payload, null, 2));
  if (payload.success === false) process.exitCode = 1;
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
