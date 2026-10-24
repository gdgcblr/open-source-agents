import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { addDownload, controlDownload, listDownloads, status, verifyDownload } from './convoy.js';

const server = new McpServer({ name: 'convoy-mcp', version: '0.1.0' });
const text = (value: unknown) => JSON.stringify(value, null, 2);
const fail = (error: unknown) => ({ content: [{ type: 'text' as const, text: error instanceof Error ? error.message : String(error) }], isError: true });

server.registerTool('convoy_status', {
  description: 'Check whether Convoy is installed and running. Set launch=true to open Convoy if needed.',
  inputSchema: { launch: z.boolean().optional().default(false) },
}, async ({ launch }) => {
  try { return { content: [{ type: 'text', text: text(await status(launch)) }] }; }
  catch (error) { return fail(error); }
});

server.registerTool('add_download', {
  description: 'Queue an HTTP or HTTPS URL in Convoy. Convoy may show a confirmation or duplicate conflict dialog.',
  inputSchema: {
    url: z.string().url(), filename: z.string().optional(),
    segmentCount: z.number().int().min(1).max(16).optional(),
  },
}, async ({ url, filename, segmentCount }) => {
  try { return { content: [{ type: 'text', text: text(await addDownload(url, filename, segmentCount)) }] }; }
  catch (error) { return fail(error); }
});

server.registerTool('list_downloads', {
  description: 'List Convoy downloads, including completed tasks. Convoy must be running.',
  inputSchema: { status: z.string().optional() },
}, async ({ status: filter }) => {
  try {
    const downloads = await listDownloads();
    const filtered = filter ? downloads.filter((item) => item.status === filter) : downloads;
    return { content: [{ type: 'text', text: text(filtered) }] };
  } catch (error) { return fail(error); }
});

for (const action of ['pause', 'resume', 'cancel'] as const) {
  server.registerTool(`${action}_download`, {
    description: action === 'cancel'
      ? 'Cancel a Convoy download. This deletes its partial download data.'
      : `${action === 'pause' ? 'Pause' : 'Resume'} an active Convoy download by ID.`,
    inputSchema: { id: z.string().min(1) },
  }, async ({ id }) => {
    try {
      await controlDownload(action, id);
      return { content: [{ type: 'text', text: `${action} request accepted for download ${id}` }] };
    } catch (error) { return fail(error); }
  });
}

server.registerTool('verify_download', {
  description: 'Compare a completed Convoy download with a published SHA-256. The file is selected by Convoy download ID; raw paths are not accepted.',
  inputSchema: { id: z.string().min(1), expected_sha256: z.string().length(64) },
}, async ({ id, expected_sha256 }) => {
  try { return { content: [{ type: 'text', text: text(await verifyDownload(id, expected_sha256)) }] }; }
  catch (error) { return fail(error); }
});

await server.connect(new StdioServerTransport());
