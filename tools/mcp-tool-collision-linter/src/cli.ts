#!/usr/bin/env node
import { writeFile } from "node:fs/promises";
import { parseArgs } from "node:util";
import { assignIds, loadFromMcpConfig, loadManifest } from "./collect.js";
import { lint } from "./index.js";
import { loadProbeFile } from "./probes.js";
import { createProvider, detectProvider, type ProviderName } from "./providers.js";
import { formatText, toJson, toMarkdown } from "./report.js";
import type { PairEvaluation, ToolDef } from "./types.js";
try {
  (process as any).loadEnvFile?.();
} catch (err: any) {
  if (err?.code !== "ENOENT") throw err;
}

const HELP = `mcp-collide: find MCP tools a model is likely to confuse, and measure how often it does.

Input (one of):
  --config <file>          MCP config with an "mcpServers" block (Claude Desktop / Cursor / VS Code format).
                           Servers are started, their tools listed, then shut down.
  --tools <file>           Tool snapshot: { "servers": { "<name>": [ {name, description, inputSchema} ] } }

Model:
  --provider <name>        anthropic | openai | offline   (default: picked from ANTHROPIC_API_KEY / OPENAI_API_KEY)
  --model <id>             Model id (or ANTHROPIC_MODEL / OPENAI_MODEL)
  --base-url <url>         API base URL, e.g. http://localhost:11434/v1 for Ollama
  --temperature <n>        Sent only if set

What to check:
  --static                 Similarity scan only, no model calls
  --threshold <0..1>       Minimum static similarity to count as look-alike   (default 0.3)
  --max-pairs <n>          Probe the n most similar pairs                       (default 10)
  --probes-per-tool <n>    Generated prompts per tool per pair                  (default 4)
  --probes <file>          Hand-written probes: [{ "prompt": "...", "intended": "server/tool" }]
  --context <all|pair>     Model sees all tools (realistic) or only the pair    (default all)
  --include-same-server    Also compare tools on the same server
  --server <name>          Only load this server (repeatable)
  --no-rewrites            Skip description rewrite suggestions
  --verify-rewrites        Re-run probes with the suggested descriptions and report before/after

Output:
  --format <text|json|markdown>   (default text)
  --out <file>             Write the report to a file instead of stdout
  --dump-tools <file>      Save the collected tools as a snapshot for --tools
  --fail-on <high|medium|low>     Exit 1 if any pair reaches this severity (for CI)
  --concurrency <n>        Parallel model calls                                 (default 4)
  --timeout <ms>           Per-server connect/list timeout                      (default 30000)
  -h, --help
`;

const SEVERITY_RANK: Record<PairEvaluation["severity"], number> = { none: 0, low: 1, medium: 2, high: 3 };

function num(v: string | undefined, name: string, fallback: number): number {
  if (v === undefined) return fallback;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`--${name} must be a number`);
  return n;
}

async function main(): Promise<number> {
  const { values: a } = parseArgs({
    options: {
      config: { type: "string" },
      tools: { type: "string" },
      provider: { type: "string" },
      model: { type: "string" },
      "base-url": { type: "string" },
      temperature: { type: "string" },
      static: { type: "boolean", default: false },
      threshold: { type: "string" },
      "max-pairs": { type: "string" },
      "probes-per-tool": { type: "string" },
      probes: { type: "string" },
      context: { type: "string" },
      "include-same-server": { type: "boolean", default: false },
      server: { type: "string", multiple: true },
      "no-rewrites": { type: "boolean", default: false },
      "verify-rewrites": { type: "boolean", default: false },
      format: { type: "string", default: "text" },
      out: { type: "string" },
      "dump-tools": { type: "string" },
      "fail-on": { type: "string" },
      concurrency: { type: "string" },
      timeout: { type: "string" },
      help: { type: "boolean", short: "h", default: false },
    },
    strict: true,
  });

  if (a.help || (!a.config && !a.tools)) {
    process.stdout.write(HELP);
    return a.help ? 0 : 2;
  }
  if (a.config && a.tools) throw new Error("Use either --config or --tools, not both");
  if (!["text", "json", "markdown"].includes(a.format!)) throw new Error("--format must be text, json or markdown");
  const context = (a.context ?? "all") as "all" | "pair";
  if (!["all", "pair"].includes(context)) throw new Error("--context must be all or pair");
  if (a["fail-on"] && !(a["fail-on"] in SEVERITY_RANK)) throw new Error("--fail-on must be high, medium or low");

  const log = (msg: string) => process.stderr.write(`${msg}\n`);

  let tools: ToolDef[];
  if (a.config) {
    log(`Connecting to servers in ${a.config}…`);
    tools = await loadFromMcpConfig(a.config, {
      timeoutMs: num(a.timeout, "timeout", 30_000),
      only: a.server,
      onError: (server, err) => log(`  ! skipped "${server}": ${(err as Error).message}`),
    });
  } else {
    tools = await loadManifest(a.tools!);
    if (a.server?.length) tools = tools.filter((t) => a.server!.includes(t.server));
  }
  if (tools.length === 0) throw new Error("No tools were loaded");
  log(`Loaded ${tools.length} tools from ${new Set(tools.map((t) => t.server)).size} servers.`);

  if (a["dump-tools"]) {
    const servers: Record<string, unknown[]> = {};
    for (const t of tools) (servers[t.server] ??= []).push({ name: t.name, description: t.description, inputSchema: t.inputSchema });
    await writeFile(a["dump-tools"], JSON.stringify({ servers }, null, 2) + "\n");
    log(`Saved tool snapshot to ${a["dump-tools"]}`);
  }

  const providerName = (a.static ? "offline" : (a.provider ?? detectProvider())) as ProviderName;
  const provider = createProvider(providerName, {
    model: a.model,
    baseUrl: a["base-url"],
    temperature: a.temperature !== undefined ? num(a.temperature, "temperature", 0) : undefined,
  });
  if (!a.static) log(`Using ${provider.name}`);

  const userProbes = a.probes ? await loadProbeFile(a.probes, assignIds(tools)) : undefined;

  const report = await lint(tools, provider, {
    staticOnly: a.static,
    threshold: num(a.threshold, "threshold", 0.3),
    includeSameServer: a["include-same-server"],
    maxPairs: num(a["max-pairs"], "max-pairs", 10),
    probesPerTool: num(a["probes-per-tool"], "probes-per-tool", 4),
    concurrency: num(a.concurrency, "concurrency", 4),
    context,
    userProbes,
    suggestRewrites: !a["no-rewrites"],
    verifyRewrites: a["verify-rewrites"],
    onProgress: (m) => log(`  ${m}`),
  });
  log("");

  const output = a.format === "json" ? toJson(report) : a.format === "markdown" ? toMarkdown(report) : formatText(report) + "\n";
  if (a.out) {
    await writeFile(a.out, output);
    log(`Wrote report to ${a.out}`);
    if (a.format === "text") process.stdout.write(output);
  } else {
    process.stdout.write(output);
  }

  if (a["fail-on"]) {
    const limit = SEVERITY_RANK[a["fail-on"] as PairEvaluation["severity"]];
    const failing = report.evaluations.filter((e) => SEVERITY_RANK[e.severity] >= limit);
    if (failing.length) {
      log(`${failing.length} pair(s) at or above "${a["fail-on"]}" severity.`);
      return 1;
    }
  }
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    process.stderr.write(`error: ${(err as Error).message}\n`);
    process.exit(2);
  },
);
