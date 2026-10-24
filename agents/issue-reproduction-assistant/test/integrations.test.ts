import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { test } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { buildAgentCard, createA2AServer } from "../src/a2a-server.js";
import { createProvider, readConfig, supportedProviders } from "../src/config.js";
import { createMcpServer } from "../src/mcp-server.js";
import { OllamaProvider } from "../src/ollama-provider.js";

test("config selects providers and default models per provider", () => {
  assert.equal(readConfig({}).provider, "gemini");
  assert.equal(readConfig({ AI_PROVIDER: "ollama" }).model, "gemma3");
  assert.deepEqual(supportedProviders().sort(), ["gemini", "ollama"]);
  assert.equal(createProvider(readConfig({ AI_PROVIDER: "ollama" })).providerName, "ollama");
  assert.equal(createProvider(readConfig({ GEMINI_API_KEY: "k" })).providerName, "gemini");
  assert.throws(() => createProvider(readConfig({})), /GEMINI_API_KEY is required/);
  assert.throws(() => createProvider({ provider: "nope", model: "x" }), /Supported: gemini, ollama/);
});

test("Ollama provider (Gemma) posts to /api/generate with JSON mode", async () => {
  let captured: { url: string; body: any } | undefined;
  const fakeFetch = (async (url: string, init: RequestInit) => {
    captured = { url, body: JSON.parse(String(init.body)) };
    return new Response(JSON.stringify({ response: ' {"summary":"ok"} ' }), { status: 200 });
  }) as unknown as typeof fetch;

  const provider = new OllamaProvider("gemma3", "http://localhost:11434/", fakeFetch);
  assert.equal(await provider.generateText("hi", { json: true }), '{"summary":"ok"}');
  assert.equal(captured?.url, "http://localhost:11434/api/generate");
  assert.equal(captured?.body.model, "gemma3");
  assert.equal(captured?.body.format, "json");
});

test("Ollama provider explains how to fix an unreachable server", async () => {
  const fakeFetch = (async () => {
    throw new Error("ECONNREFUSED");
  }) as unknown as typeof fetch;
  await assert.rejects(new OllamaProvider("gemma3", "http://x", fakeFetch).generateText("hi"), /ollama pull gemma3/);
});

test("MCP server lists tools and extracts signals over an in-memory transport", async () => {
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const server = createMcpServer();
  const client = new Client({ name: "test", version: "1.0.0" });
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);

  const tools = (await client.listTools()).tools.map((tool) => tool.name).sort();
  assert.deepEqual(tools, ["extract_issue_signals", "fetch_github_issue", "file_history", "investigate_issue", "locate_code"]);

  const result = (await client.callTool({
    name: "extract_issue_signals",
    arguments: { issueText: "Error: boom happened\n  at run (src/app.ts:10:5)" },
  })) as { content: Array<{ text: string }> };
  const parsed = JSON.parse(result.content[0].text);
  assert.equal(parsed.stackFrames[0].file, "src/app.ts");

  const bad = (await client.callTool({ name: "investigate_issue", arguments: {} })) as { isError?: boolean };
  assert.equal(bad.isError, true);
  await client.close();
});

test("A2A server serves an agent card and validates JSON-RPC requests", async () => {
  const server = createA2AServer({ port: 0, allowUpload: false });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  const base = `http://127.0.0.1:${port}`;

  try {
    const card = (await (await fetch(`${base}/.well-known/agent-card.json`)).json()) as { name: string; skills: unknown[] };
    assert.equal(card.name, "Issue Reproduction Assistant");
    assert.equal(card.skills.length, 1);

    const post = async (body: unknown) =>
      (await (await fetch(`${base}/`, { method: "POST", body: JSON.stringify(body) })).json()) as any;

    assert.equal((await post({ jsonrpc: "2.0", id: 1, method: "tasks/get" })).error.code, -32601);
    const noRef = await post({
      jsonrpc: "2.0", id: 2, method: "message/send",
      params: { message: { role: "user", parts: [{ kind: "text", text: "hello" }] } },
    });
    assert.equal(noRef.error.code, -32602);
    assert.equal((await fetch(`${base}/nope`)).status, 404);
  } finally {
    server.close();
  }
  assert.match(buildAgentCard("http://x/", true).skills[0].description, /model-assisted/);
});
