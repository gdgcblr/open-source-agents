import assert from "node:assert/strict";
import { test } from "node:test";
import { assignIds, expandEnv, loadFromMcpConfig, loadManifest } from "../src/collect.js";

const examples = new URL("../examples/", import.meta.url).pathname;

test("assignIds makes provider-safe, unique ids", () => {
  const ids = assignIds([
    { server: "my.server", name: "do thing", description: "", inputSchema: {} },
    { server: "my.server", name: "do thing", description: "", inputSchema: {} },
    { server: "x", name: "a".repeat(100), description: "", inputSchema: {} },
  ]).map((t) => t.id);
  assert.deepEqual(ids.slice(0, 2), ["my_server__do_thing", "my_server__do_thing_2"]);
  for (const id of ids) assert.match(id, /^[a-zA-Z0-9_-]{1,64}$/);
});

test("expandEnv substitutes ${VAR} and blanks unknown ones", () => {
  assert.equal(expandEnv("Bearer ${TOKEN}-${MISSING}", { TOKEN: "abc" }), "Bearer abc-");
});

test("manifest and live servers yield the same tools", async () => {
  const fromManifest = await loadManifest(`${examples}colliding-tools.json`);
  const fromServers = await loadFromMcpConfig(`${examples}mcp-config.json`, { timeoutMs: 20_000 });
  const key = (t: { server: string; name: string }) => `${t.server}/${t.name}`;
  assert.deepEqual(fromServers.map(key).sort(), fromManifest.map(key).sort());
  const note = fromServers.find((t) => t.name === "search_notes")!;
  assert.deepEqual(note.inputSchema.required, ["query"]);
});

test("a broken server is reported, not fatal, when onError is given", async () => {
  const { writeFile, mkdtemp } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const dir = await mkdtemp(`${tmpdir()}/collide-`);
  const cfg = `${dir}/config.json`;
  await writeFile(
    cfg,
    JSON.stringify({
      mcpServers: {
        good: { command: "node", args: ["--import", "tsx", `${examples}fixture-server.ts`, "chat"], cwd: examples },
        bad: { command: "definitely-not-a-real-binary-xyz" },
      },
    }),
  );
  const errors: string[] = [];
  const tools = await loadFromMcpConfig(cfg, { timeoutMs: 20_000, onError: (s) => errors.push(s) });
  assert.deepEqual(errors, ["bad"]);
  assert.equal(tools.length, 2);
});
