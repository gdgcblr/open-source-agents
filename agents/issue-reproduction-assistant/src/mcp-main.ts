#!/usr/bin/env node
import "dotenv/config";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./mcp-server.js";

// stdout is the MCP channel; log only to stderr.
await createMcpServer().connect(new StdioServerTransport());
console.error("issue-reproduction-assistant MCP server running on stdio");
