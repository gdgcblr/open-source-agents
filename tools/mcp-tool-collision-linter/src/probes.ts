import { readFile } from "node:fs/promises";
import type { CandidatePair, LoadedTool, Probe, Provider } from "./types.js";

const PROBE_SYSTEM = `You write test prompts for evaluating how well an AI model chooses between tools.
You are given two tools, A and B, that live on different servers and look alike.
Write realistic requests a real user might type. Users never know tool names or server names.
Each request must have one clearly correct tool if a careful expert reads both descriptions,
but should use everyday wording that overlaps with the other tool, because that is where models slip.
Vary length, tone and specificity. Do not mention "tool A", "tool B", tool names or server names.
Reply with JSON only, in this exact shape: {"a": ["...", ...], "b": ["...", ...]}`;

function describe(t: LoadedTool): string {
  return [
    `Server: ${t.server}`,
    `Name: ${t.name}`,
    `Description: ${t.description || "(none)"}`,
    `Input schema: ${JSON.stringify(t.inputSchema)}`,
  ].join("\n");
}

/** Pulls the first JSON object out of a model reply, tolerating code fences and stray prose. */
export function extractJson<T>(text: string): T {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const body = fenced ? fenced[1]! : text;
  const start = body.indexOf("{");
  const end = body.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error(`Model reply had no JSON object: ${text.slice(0, 200)}`);
  return JSON.parse(body.slice(start, end + 1)) as T;
}

async function llmProbes(pair: CandidatePair, provider: Provider, perTool: number): Promise<Probe[]> {
  const user = `Tool A\n${describe(pair.a)}\n\nTool B\n${describe(pair.b)}\n\nWrite ${perTool} requests that should go to A and ${perTool} that should go to B.`;
  const reply = await provider.complete!(PROBE_SYSTEM, user);
  const parsed = extractJson<{ a?: unknown; b?: unknown }>(reply);
  const pick = (list: unknown, intended: string): Probe[] =>
    (Array.isArray(list) ? list : [])
      .filter((p): p is string => typeof p === "string" && p.trim().length > 0)
      .slice(0, perTool)
      .map((prompt) => ({ prompt: prompt.trim(), intended }));
  const probes = [...pick(parsed.a, pair.a.id), ...pick(parsed.b, pair.b.id)];
  if (probes.length === 0) throw new Error(`No usable probes generated for ${pair.a.id} vs ${pair.b.id}`);
  return probes;
}

const LEAD_INS = [
  /^(use (this|this tool|me) (to|for|when)\s+)/i,
  /^(this tool (lets you|allows you to|can|will)?\s*)/i,
  /^(tool (to|for)\s+)/i,
  /^(allows (you|the user) to\s+)/i,
  /^(lets you\s+)/i,
];

/** Turns "Searches the user's notes by keyword." into "search the user's notes by keyword". */
function toTask(description: string, fallbackName: string): string {
  let s = (description.split(/(?<=[.!?])\s+/)[0] ?? "").trim().replace(/[.!?]+$/, "");
  for (const re of LEAD_INS) s = s.replace(re, "");
  if (!s) s = fallbackName.replace(/[_-]+/g, " ");
  const [first, ...rest] = s.split(" ");
  const verb = (first ?? "")
    .toLowerCase()
    .replace(/ies$/, "y")
    .replace(/(ch|sh|ss|x)es$/, "$1")
    .replace(/([^s])s$/, "$1");
  return [verb, ...rest].join(" ").replace(/\bthe user's\b/gi, "my").replace(/\buser's\b/gi, "my");
}

/** Template probes for offline mode. They exercise the pipeline; real measurement needs a model. */
export function templateProbes(pair: CandidatePair, perTool: number): Probe[] {
  const templates = [
    (task: string) => `Can you ${task}?`,
    (task: string) => `I need to ${task}.`,
    (task: string) => `Please ${task} for me.`,
    (task: string) => `Quick one: ${task}`,
    (task: string) => `How would I ${task}? Just do it.`,
  ];
  const out: Probe[] = [];
  for (const t of [pair.a, pair.b]) {
    const task = toTask(t.description, t.name);
    for (let i = 0; i < Math.min(perTool, templates.length); i++) out.push({ prompt: templates[i]!(task), intended: t.id });
  }
  return out;
}

export async function generateProbes(pair: CandidatePair, provider: Provider, perTool: number): Promise<Probe[]> {
  return provider.complete ? llmProbes(pair, provider, perTool) : templateProbes(pair, perTool);
}

/** Resolves "server/name", "server__name", the assigned id, or a bare name if unique. */
export function resolveToolRef(ref: string, tools: LoadedTool[]): LoadedTool | undefined {
  const byId = tools.find((t) => t.id === ref);
  if (byId) return byId;
  const m = ref.match(/^([^/]+)\/(.+)$/) ?? ref.match(/^(.+?)__(.+)$/);
  if (m) return tools.find((t) => t.server === m[1] && t.name === m[2]);
  const byName = tools.filter((t) => t.name === ref);
  return byName.length === 1 ? byName[0] : undefined;
}

/**
 * Hand-written probes: `[{ "prompt": "...", "intended": "server/tool" }]`.
 * These are the most trustworthy test set, because a human decided the right answer.
 */
export async function loadProbeFile(file: string, tools: LoadedTool[]): Promise<Probe[]> {
  const raw = JSON.parse(await readFile(file, "utf8")) as unknown;
  const list = Array.isArray(raw) ? raw : (raw as { probes?: unknown[] })?.probes;
  if (!Array.isArray(list)) throw new Error(`${file}: expected an array of { prompt, intended }`);
  return list.map((p, i) => {
    const { prompt, intended } = (p ?? {}) as { prompt?: unknown; intended?: unknown };
    if (typeof prompt !== "string" || typeof intended !== "string") {
      throw new Error(`${file}: entry ${i} needs string "prompt" and "intended"`);
    }
    const tool = resolveToolRef(intended, tools);
    if (!tool) throw new Error(`${file}: entry ${i} names unknown tool "${intended}"`);
    return { prompt, intended: tool.id };
  });
}
