#!/usr/bin/env node
// CLI entry. Parses flags by hand. Only this file and view.js write to the terminal.
// Flags: --mock (offline model, forced when no GEMINI_API_KEY), --once "<text>", --session <id>.

import readline from 'node:readline/promises';
import { createAgent } from './agent.js';
import { loadConfig, loadDotEnv } from './config.js';
import { createLogger } from './logger.js';
import { createMcpClient } from './mcp-client.js';
import { createGeminiModel } from './llm/gemini.js';
import { createMockModel } from './llm/mock.js';
import { HELP_LINES, formatNavigation, formatPins } from './view.js';

export function parseArgs(argv) {
  const out = { mock: false, once: null, session: null };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === '--mock') out.mock = true;
    else if (flag === '--once') out.once = argv[++i] ?? '';
    else if (flag === '--session') out.session = argv[++i] ?? null;
    else throw new Error(`unknown flag: ${flag}`);
  }
  return out;
}

const write = (line = '') => process.stdout.write(`${line}\n`);

function printTurn(result) {
  write(result.reply);
  for (const nav of result.navigation) {
    for (const line of formatNavigation(nav)) write(line);
  }
}

async function main() {
  loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  const config = loadConfig();
  const logger = createLogger(config.logLevel);
  const useMock = args.mock || !config.apiKey;
  if (!args.mock && !config.apiKey) process.stderr.write('GEMINI_API_KEY is not set: using the offline mock model.\n');

  const model = useMock
    ? createMockModel()
    : createGeminiModel({ apiKey: config.apiKey, modelName: config.modelName });
  const mcp = createMcpClient({ serverPath: config.serverPath, dataDir: config.dataDir });
  await mcp.connect();

  const rl = args.once === null ? readline.createInterface({ input: process.stdin, output: process.stdout }) : null;
  const confirm = async ({ name, args: callArgs }) => {
    if (!rl) return false;
    const answer = await rl.question(`Confirm ${name} ${JSON.stringify(callArgs)}? (y/N) `);
    return /^y(es)?$/i.test(answer.trim());
  };
  const agent = createAgent({ model, mcp, maxToolCalls: config.maxToolCalls, confirm, logger });
  await agent.init({ sessionId: args.session });

  try {
    if (args.once !== null) {
      printTurn(await agent.turn(args.once));
      return;
    }
    write(`Pinpoint agent (${model.name}). Session ${agent.getSessionId()}. /help for commands.`);
    for (;;) {
      const line = (await rl.question('you> ')).trim();
      if (line === '') continue;
      if (line === '/exit') break;
      if (line === '/help') {
        for (const help of HELP_LINES) write(help);
        continue;
      }
      if (line === '/pins') {
        for (const row of formatPins((await agent.listPins()).pins)) write(row);
        continue;
      }
      printTurn(await agent.turn(line));
    }
  } finally {
    rl?.close();
    await mcp.close();
  }
}

if (process.argv[1] && process.argv[1].endsWith('index.js')) {
  main().catch((error) => {
    process.stderr.write(`pinpoint-agent: ${error.message}\n`);
    process.exit(1);
  });
}
