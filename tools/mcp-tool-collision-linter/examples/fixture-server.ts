/**
 * A minimal stdio MCP server that serves one server's tools from colliding-tools.json.
 * It exists so the --config path can be tried and tested without installing third-party servers.
 *
 *   node --import tsx examples/fixture-server.ts notes
 */
import { readFileSync } from "node:fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const which = process.argv[2];
const fixture = JSON.parse(readFileSync(new URL("./colliding-tools.json", import.meta.url), "utf8")) as {
  servers: Record<string, { name: string; description: string; inputSchema: Record<string, unknown> }[]>;
};
const tools = which ? fixture.servers[which] : undefined;
if (!tools) {
  console.error(`usage: fixture-server.ts <${Object.keys(fixture.servers).join("|")}>`);
  process.exit(1);
}

const server = new Server({ name: `fixture-${which}`, version: "0.1.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
server.setRequestHandler(CallToolRequestSchema, async (req) => ({
  content: [{ type: "text", text: `fixture-${which}: ${req.params.name} called (no-op)` }],
}));

await server.connect(new StdioServerTransport());
