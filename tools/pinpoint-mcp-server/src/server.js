// Builds the MCP server and registers all 13 tools. Pure: no transport, no process I/O.

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import * as pinTools from './tools/pin-tools.js';
import * as queryTools from './tools/query-tools.js';
import * as sessionTools from './tools/session-tools.js';
import * as transferTools from './tools/transfer-tools.js';

export const SERVER_NAME = 'pinpoint-mcp-server';
export const SERVER_VERSION = '0.1.0';

/**
 * @param {{ store, audit, config, logger, clock? }} deps
 */
export function createServer(deps) {
  const resolved = { clock: Date.now, ...deps };
  const server = new McpServer({ name: SERVER_NAME, version: SERVER_VERSION });
  for (const group of [sessionTools, pinTools, queryTools, transferTools]) {
    group.register(server, resolved);
  }
  return server;
}
