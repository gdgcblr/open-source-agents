import { assignIds } from "./collect.js";
import { evaluatePairs, type EvaluateOptions } from "./evaluate.js";
import { findCandidates, type CandidateOptions } from "./similarity.js";
import type { LintReport, Probe, Provider, ToolDef } from "./types.js";

export * from "./types.js";
export { loadManifest, loadFromMcpConfig, listServerTools, assignIds } from "./collect.js";
export { findCandidates, tokenize } from "./similarity.js";
export { createProvider, detectProvider, OfflineProvider, AnthropicProvider, OpenAICompatibleProvider } from "./providers.js";
export { evaluatePairs } from "./evaluate.js";
export { loadProbeFile, templateProbes } from "./probes.js";
export { formatText, toJson, toMarkdown } from "./report.js";

export interface LintOptions extends CandidateOptions, Partial<Omit<EvaluateOptions, "userProbes">> {
  /** Skip model calls and only report statically similar pairs. */
  staticOnly?: boolean;
  /** Probe at most this many of the most similar pairs. */
  maxPairs?: number;
  /** Hand-written probes with `intended` as "server/tool". Resolved against the loaded tools by the caller. */
  userProbes?: Probe[];
}

export async function lint(tools: ToolDef[], provider: Provider, opts: LintOptions = {}): Promise<LintReport> {
  const loaded = assignIds(tools);
  const candidates = findCandidates(loaded, opts);
  const toProbe = opts.staticOnly ? [] : candidates.slice(0, opts.maxPairs ?? 10);
  const evaluations = await evaluatePairs(toProbe, loaded, provider, {
    probesPerTool: opts.probesPerTool ?? 4,
    concurrency: opts.concurrency ?? 4,
    context: opts.context ?? "all",
    userProbes: opts.userProbes,
    suggestRewrites: opts.suggestRewrites ?? true,
    verifyRewrites: opts.verifyRewrites ?? false,
    onProgress: opts.onProgress,
  });
  evaluations.sort((x, y) => y.confusionRate - x.confusionRate || y.pair.score - x.pair.score);
  return {
    generatedAt: new Date().toISOString(),
    provider: provider.name,
    toolCount: loaded.length,
    servers: [...new Set(loaded.map((t) => t.server))],
    candidates,
    evaluations,
  };
}
