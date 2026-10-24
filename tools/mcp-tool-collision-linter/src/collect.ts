import { readFile } from "node:fs/promises";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { LoadedTool, ToolDef } from "./types.js";

/** Same shape as the `mcpServers` block used by Claude Desktop, Cursor, VS Code and others. */
export interface McpServerConfig {
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  cwd?: string;
  url?: string;
  headers?: Record<string, string>;
}

export interface McpConfigFile {
  mcpServers: Record<string, McpServerConfig>;
}

/**
 * A static snapshot of tools, so the linter can run without starting servers.
 * Each server maps to either an array of tools or a raw `tools/list` result (`{ tools: [...] }`).
 */
export interface ToolManifestFile {
  servers: Record<string, unknown[] | { tools: unknown[] }>;
}

const ENV_REF = /\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

/** Expands `${VAR}` references so secrets stay in the environment, not in the config file. */
export function expandEnv(value: string, env: NodeJS.ProcessEnv = process.env): string {
  return value.replace(ENV_REF, (_, key: string) => env[key] ?? "");
}

function normalizeTool(server: string, raw: unknown): ToolDef {
  const t = raw as { name?: unknown; description?: unknown; inputSchema?: unknown; input_schema?: unknown };
  if (typeof t?.name !== "string" || t.name.length === 0) {
    throw new Error(`Server "${server}" has a tool without a name`);
  }
  const schema = (t.inputSchema ?? t.input_schema) as Record<string, unknown> | undefined;
  return {
    server,
    name: t.name,
    description: typeof t.description === "string" ? t.description : "",
    inputSchema: schema && typeof schema === "object" ? schema : { type: "object", properties: {} },
  };
}

export async function loadManifest(file: string): Promise<ToolDef[]> {
  const data = JSON.parse(await readFile(file, "utf8")) as ToolManifestFile;
  if (!data || typeof data.servers !== "object") {
    throw new Error(`${file}: expected a top-level "servers" object`);
  }
  const tools: ToolDef[] = [];
  for (const [server, entry] of Object.entries(data.servers)) {
    const list = Array.isArray(entry) ? entry : entry?.tools;
    if (!Array.isArray(list)) throw new Error(`${file}: server "${server}" must be an array of tools or { tools: [...] }`);
    for (const raw of list) tools.push(normalizeTool(server, raw));
  }
  return tools;
}

async function withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      p,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms}ms`)), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function listServerTools(
  server: string,
  cfg: McpServerConfig,
  opts: { timeoutMs?: number; baseDir?: string } = {},
): Promise<ToolDef[]> {
  const timeoutMs = opts.timeoutMs ?? 30_000;
  const client = new Client({ name: "mcp-tool-collision-linter", version: "0.1.0" });

  let transport;
  if (cfg.url) {
    const headers = Object.fromEntries(Object.entries(cfg.headers ?? {}).map(([k, v]) => [k, expandEnv(v)]));
    transport = new StreamableHTTPClientTransport(new URL(expandEnv(cfg.url)), { requestInit: { headers } });
  } else if (cfg.command) {
    const env: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
    for (const [k, v] of Object.entries(cfg.env ?? {})) env[k] = expandEnv(v);
    transport = new StdioClientTransport({
      command: cfg.command,
      args: (cfg.args ?? []).map((a) => expandEnv(a)),
      env,
      cwd: cfg.cwd ? path.resolve(opts.baseDir ?? process.cwd(), cfg.cwd) : opts.baseDir,
      stderr: "ignore",
    });
  } else {
    throw new Error(`Server "${server}" needs either "command" or "url"`);
  }

  try {
    await withTimeout(client.connect(transport), timeoutMs, `Connecting to "${server}"`);
    const tools: ToolDef[] = [];
    let cursor: string | undefined;
    do {
      const page = await withTimeout(client.listTools(cursor ? { cursor } : undefined), timeoutMs, `Listing tools on "${server}"`);
      for (const t of page.tools) tools.push(normalizeTool(server, t));
      cursor = page.nextCursor;
    } while (cursor);
    return tools;
  } finally {
    await client.close().catch(() => undefined);
  }
}

export async function loadFromMcpConfig(
  file: string,
  opts: { timeoutMs?: number; only?: string[]; onError?: (server: string, err: unknown) => void } = {},
): Promise<ToolDef[]> {
  const data = JSON.parse(await readFile(file, "utf8")) as McpConfigFile;
  if (!data || typeof data.mcpServers !== "object") {
    throw new Error(`${file}: expected a top-level "mcpServers" object`);
  }
  const baseDir = path.dirname(path.resolve(file));
  const entries = Object.entries(data.mcpServers).filter(([name]) => !opts.only?.length || opts.only.includes(name));

  const results = await Promise.allSettled(
    entries.map(([name, cfg]) => listServerTools(name, cfg, { timeoutMs: opts.timeoutMs, baseDir })),
  );
  const tools: ToolDef[] = [];
  results.forEach((r, i) => {
    const server = entries[i]![0];
    if (r.status === "fulfilled") tools.push(...r.value);
    else if (opts.onError) opts.onError(server, r.reason);
    else throw r.reason;
  });
  return tools;
}

/** Tool names must match ^[a-zA-Z0-9_-]{1,64}$ for both Anthropic and OpenAI. */
export function assignIds(tools: ToolDef[]): LoadedTool[] {
  const used = new Set<string>();
  return tools.map((t) => {
    const base = `${t.server}__${t.name}`.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 60);
    let id = base;
    for (let n = 2; used.has(id); n++) id = `${base.slice(0, 60)}_${n}`;
    used.add(id);
    return { ...t, id };
  });
}
