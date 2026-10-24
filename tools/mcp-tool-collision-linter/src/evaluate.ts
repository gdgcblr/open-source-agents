import { extractJson, generateProbes } from "./probes.js";
import { round } from "./similarity.js";
import type {
  CandidatePair,
  LoadedTool,
  PairEvaluation,
  Probe,
  ProbeResult,
  Provider,
  RewriteSuggestion,
} from "./types.js";

export async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T, i: number) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i]!, i);
    }
  });
  await Promise.all(workers);
  return out;
}

export interface EvaluateOptions {
  probesPerTool: number;
  concurrency: number;
  /** "all": the model sees every loaded tool (realistic). "pair": only the two tools (isolates the pair). */
  context: "all" | "pair";
  /** Hand-written probes; used instead of generated ones for any pair they cover. */
  userProbes?: Probe[];
  suggestRewrites: boolean;
  verifyRewrites: boolean;
  onProgress?: (msg: string) => void;
}

/**
 * Severity is driven by A↔B swaps, since that is the collision this pair is about.
 * A pair whose probes mostly land on some third tool is still flagged low, so it is not reported as clean.
 */
export function severity(confusion: number, accuracy: number): PairEvaluation["severity"] {
  if (confusion >= 0.25) return "high";
  if (confusion >= 0.1) return "medium";
  if (confusion > 0 || accuracy < 0.75) return "low";
  return "none";
}

function score(pair: CandidatePair, results: ProbeResult[]) {
  const total = results.length || 1;
  const aToB = results.filter((r) => r.intended === pair.a.id && r.chosen === pair.b.id).length;
  const bToA = results.filter((r) => r.intended === pair.b.id && r.chosen === pair.a.id).length;
  const correct = results.filter((r) => r.chosen === r.intended).length;
  return {
    aToB,
    bToA,
    elsewhere: results.length - correct - aToB - bToA,
    confusionRate: round((aToB + bToA) / total),
    accuracy: round(correct / total),
  };
}

async function runProbes(
  probes: Probe[],
  tools: LoadedTool[],
  provider: Provider,
  concurrency: number,
): Promise<ProbeResult[]> {
  return mapLimit(probes, concurrency, async (probe) => ({
    ...probe,
    chosen: await provider.chooseTool({ prompt: probe.prompt, tools }),
  }));
}

const REWRITE_SYSTEM = `You improve MCP tool descriptions so AI models stop confusing two similar tools.
Rules:
- Keep every description truthful. Never add capabilities the tool does not have.
- Lead with what the tool does and which data or system it acts on.
- Add a short "Use when ..." and "Not for ..." boundary that separates it from the other tool.
- Do not mention the other tool's name or server name; the two servers do not know about each other.
  Describe the boundary by data source, scope or intent instead.
- Keep each description under 450 characters.
Reply with JSON only: {"descriptions": {"<tool id>": "...", "<tool id>": "..."}, "rationale": "one or two sentences"}`;

async function suggestRewrite(
  ev: PairEvaluation,
  provider: Provider,
): Promise<RewriteSuggestion | undefined> {
  if (!provider.complete) return undefined;
  const { a, b } = ev.pair;
  const misses = ev.probes
    .filter((p) => p.chosen !== p.intended)
    .slice(0, 6)
    .map((p) => `- "${p.prompt}" → should be ${p.intended}, model chose ${p.chosen ?? "nothing"}`)
    .join("\n");
  const user = [
    `Tool id: ${a.id}\nServer: ${a.server}\nDescription: ${a.description}\nInput schema: ${JSON.stringify(a.inputSchema)}`,
    `Tool id: ${b.id}\nServer: ${b.server}\nDescription: ${b.description}\nInput schema: ${JSON.stringify(b.inputSchema)}`,
    misses ? `Requests the model got wrong:\n${misses}` : "The model made no outright mistakes, but these tools look alike.",
  ].join("\n\n");
  const parsed = extractJson<{ descriptions?: Record<string, unknown>; rationale?: unknown }>(
    await provider.complete(REWRITE_SYSTEM, user),
  );
  const descriptions: Record<string, string> = {};
  for (const id of [a.id, b.id]) {
    const d = parsed.descriptions?.[id];
    if (typeof d === "string" && d.trim()) descriptions[id] = d.trim();
  }
  if (Object.keys(descriptions).length === 0) return undefined;
  return { descriptions, rationale: typeof parsed.rationale === "string" ? parsed.rationale : "" };
}

export async function evaluatePairs(
  pairs: CandidatePair[],
  allTools: LoadedTool[],
  provider: Provider,
  opts: EvaluateOptions,
): Promise<PairEvaluation[]> {
  const results: PairEvaluation[] = [];
  for (const [i, pair] of pairs.entries()) {
    const label = `[${i + 1}/${pairs.length}] ${pair.a.server}/${pair.a.name} vs ${pair.b.server}/${pair.b.name}`;
    opts.onProgress?.(`${label}: probing`);

    const handWritten = opts.userProbes?.filter((p) => p.intended === pair.a.id || p.intended === pair.b.id) ?? [];
    const probes = handWritten.length > 0 ? handWritten : await generateProbes(pair, provider, opts.probesPerTool);
    const tools = opts.context === "all" ? allTools : [pair.a, pair.b];
    const probeResults = await runProbes(probes, tools, provider, opts.concurrency);
    const metrics = score(pair, probeResults);

    const ev: PairEvaluation = {
      pair,
      probes: probeResults,
      ...metrics,
      severity: severity(metrics.confusionRate, metrics.accuracy),
    };

    if (opts.suggestRewrites && metrics.confusionRate > 0 && provider.complete) {
      opts.onProgress?.(`${label}: drafting rewrites`);
      try {
        ev.rewrite = await suggestRewrite(ev, provider);
      } catch (err) {
        opts.onProgress?.(`${label}: rewrite failed (${(err as Error).message})`);
      }
      if (ev.rewrite && opts.verifyRewrites) {
        opts.onProgress?.(`${label}: re-testing with rewrites`);
        const patched = tools.map((t) =>
          ev.rewrite!.descriptions[t.id] ? { ...t, description: ev.rewrite!.descriptions[t.id]! } : t,
        );
        const after = score(pair, await runProbes(probes, patched, provider, opts.concurrency));
        ev.rewrite.after = { confusionRate: after.confusionRate, accuracy: after.accuracy };
      }
    }
    results.push(ev);
  }
  return results;
}
