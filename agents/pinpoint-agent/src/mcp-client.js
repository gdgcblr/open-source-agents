// Spawns the Pinpoint server over stdio. The child gets the SDK's default environment plus
// PINPOINT_DATA_DIR and nothing else. The Gemini key is never passed through.

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport, getDefaultEnvironment } from '@modelcontextprotocol/sdk/client/stdio.js';

export function buildChildEnv(dataDir) {
  const env = { ...getDefaultEnvironment() };
  if (dataDir) env.PINPOINT_DATA_DIR = dataDir;
  return env;
}

export function createMcpClient({ serverPath, dataDir, command = process.execPath, stderr = 'ignore' }) {
  const client = new Client({ name: 'pinpoint-agent', version: '0.1.0' });
  let transport = null;

  return {
    async connect() {
      transport = new StdioClientTransport({
        command,
        args: [serverPath],
        env: buildChildEnv(dataDir),
        stderr,
      });
      await client.connect(transport);
    },

    async listTools() {
      const { tools } = await client.listTools();
      return tools.map((t) => ({ name: t.name, description: t.description ?? '', inputSchema: t.inputSchema }));
    },

    /** Returns { isError, body, text }. body is the server's parsed JSON envelope. */
    async callTool(name, args) {
      const result = await client.callTool({ name, arguments: args });
      const text = result.content?.[0]?.text ?? '';
      let body;
      try {
        body = JSON.parse(text);
      } catch {
        body = { ok: false, error: { code: 'BAD_RESPONSE', message: 'server reply was not JSON' } };
      }
      return { isError: result.isError === true, body, text };
    },

    async close() {
      await client.close().catch(() => {});
      transport = null;
    },

    isConnected: () => transport !== null,
  };
}
