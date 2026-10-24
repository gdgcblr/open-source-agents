import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";
import { AnthropicProvider, OpenAICompatibleProvider } from "../src/providers.js";
import type { LoadedTool } from "../src/types.js";

const tools: LoadedTool[] = [
  { id: "notes__search_notes", server: "notes", name: "search_notes", description: "Search notes", inputSchema: { type: "object", properties: {} } },
  { id: "drive__search_files", server: "drive", name: "search_files", description: "Search files", inputSchema: {} },
];

type Handler = (body: any, req: IncomingMessage, res: ServerResponse) => void;

async function mockServer(handler: Handler) {
  const bodies: any[] = [];
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      const body = JSON.parse(raw);
      bodies.push({ path: req.url, headers: req.headers, body });
      handler(body, req, res);
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { url, bodies, close: () => new Promise((r) => server.close(r)) };
}

const json = (res: ServerResponse, status: number, data: unknown) => {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(data));
};

test("OpenAI-compatible: sends tools as functions and reads the tool call", async () => {
  const srv = await mockServer((_b, _q, res) =>
    json(res, 200, { choices: [{ message: { tool_calls: [{ function: { name: "drive__search_files", arguments: "{}" } }] } }] }),
  );
  try {
    const p = new OpenAICompatibleProvider({ baseUrl: srv.url, model: "test-model", apiKey: "k" });
    assert.equal(await p.chooseTool({ prompt: "find my budget", tools }), "drive__search_files");
    const sent = srv.bodies[0];
    assert.equal(sent.path, "/chat/completions");
    assert.equal(sent.headers.authorization, "Bearer k");
    assert.equal(sent.body.tool_choice, "required");
    assert.equal(sent.body.tools[1].function.name, "drive__search_files");
    assert.deepEqual(sent.body.tools[1].function.parameters, { type: "object", properties: {} });
    assert.equal("temperature" in sent.body, false);
  } finally {
    await srv.close();
  }
});

test("OpenAI-compatible: falls back to tool_choice auto when required is rejected", async () => {
  const srv = await mockServer((body, _q, res) =>
    body.tool_choice === "required"
      ? json(res, 400, { error: { message: "tool_choice required not supported" } })
      : json(res, 200, { choices: [{ message: { tool_calls: [{ function: { name: "notes__search_notes" } }] } }] }),
  );
  try {
    const p = new OpenAICompatibleProvider({ baseUrl: srv.url, model: "llama", maxRetries: 0 });
    assert.equal(await p.chooseTool({ prompt: "x", tools }), "notes__search_notes");
    assert.equal(await p.chooseTool({ prompt: "y", tools }), "notes__search_notes");
    assert.deepEqual(srv.bodies.map((b) => b.body.tool_choice), ["required", "auto", "auto"]);
  } finally {
    await srv.close();
  }
});

test("Anthropic: forces a tool, parses tool_use, and retries on 429", async () => {
  let calls = 0;
  const srv = await mockServer((_b, _q, res) => {
    calls++;
    if (calls === 1) {
      res.writeHead(429, { "retry-after": "0" });
      return res.end("{}");
    }
    json(res, 200, { content: [{ type: "text", text: "ok" }, { type: "tool_use", name: "notes__search_notes", input: {} }] });
  });
  try {
    const p = new AnthropicProvider({ baseUrl: srv.url, apiKey: "sk-test", model: "m", temperature: 0 });
    assert.equal(await p.chooseTool({ prompt: "find my note", tools }), "notes__search_notes");
    const sent = srv.bodies.at(-1);
    assert.equal(sent.path, "/v1/messages");
    assert.equal(sent.headers["x-api-key"], "sk-test");
    assert.deepEqual(sent.body.tool_choice, { type: "any" });
    assert.equal(sent.body.tools[0].name, "notes__search_notes");
    assert.equal(sent.body.temperature, 0);
    assert.equal(calls, 2);
  } finally {
    await srv.close();
  }
});
