#!/usr/bin/env node
import { readLog } from './reader.js';
import type { LogEvent } from './types.js';

function safeTerminal(value: string): string {
  return value.slice(0, 1024).replace(/[\x00-\x1f\x7f-\x9f]/g, '');
}

function formatEvent(event: LogEvent): string {
  const status = event.phase === 'started' ? 'started' : event.status;
  const duration = event.durationMs === undefined ? '' : ` ${event.durationMs}ms`;
  return `${event.sequence} ${event.kind} ${safeTerminal(event.name)}${detail(event)} ${status}${duration}`;
}

function detail(event: LogEvent): string {
  const data = event.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return '';
  const attributes = data.attributes;
  if (!attributes || typeof attributes !== 'object' || Array.isArray(attributes))
    return '';
  const label = attributes.tool ?? attributes.model ?? attributes.agent;
  const name = typeof label === 'string' ? ` [${safeTerminal(label)}]` : '';
  const reason =
    typeof attributes.errorMessage === 'string'
      ? `: ${safeTerminal(attributes.errorMessage)}`
      : '';
  return `${name}${reason}`;
}

async function main(args: string[]): Promise<void> {
  if (args[0] === '--help' || args.length === 0) {
    console.log('Usage: agent-logger view <log.jsonl>');
    return;
  }
  if (args[0] !== 'view' || !args[1] || args.length !== 2)
    throw new Error('Usage: agent-logger view <log.jsonl>');
  const events = await readLog(args[1]);
  for (const event of events) console.log(formatEvent(event));
  const failures = events.filter((event) => event.status === 'failed').length;
  console.log(`Events: ${events.length}; failed operations: ${failures}`);
}

try {
  await main(process.argv.slice(2));
} catch {
  console.error('Could not read log. Check the command, file path, and JSONL schema.');
  process.exitCode = 1;
}
