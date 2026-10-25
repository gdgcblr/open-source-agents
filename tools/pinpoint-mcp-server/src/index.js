#!/usr/bin/env node
// Entry point: load config, open the store, serve MCP over stdio. stdout is the protocol; logs go to stderr.

import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createAudit } from './audit.js';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { createServer } from './server.js';
import { createStore } from './store.js';

async function main() {
  const config = loadConfig();
  const logger = createLogger(config.logLevel);
  const store = createStore({ dataDir: config.dataDir, logger });
  store.load();
  const audit = createAudit({ dataDir: config.dataDir, enabled: config.audit });
  const server = createServer({ store, audit, config, logger });

  const shutdown = async () => {
    await server.close();
    process.exit(0);
  };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);

  await server.connect(new StdioServerTransport());
  logger.info('pinpoint-mcp-server ready', { redaction: config.redact, audit: config.audit });
}

main().catch((error) => {
  process.stderr.write(`pinpoint-mcp-server failed to start: ${error.code ?? error.name}: ${error.message}\n`);
  process.exit(1);
});
