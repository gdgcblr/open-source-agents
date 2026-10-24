import type { CandidatePair, LintReport, LoadedTool, PairEvaluation } from "./types.js";

const useColor = process.stdout.isTTY && !process.env.NO_COLOR;
const paint = (code: number) => (s: string) => (useColor ? `\x1b[${code}m${s}\x1b[0m` : s);
const c = { red: paint(31), yellow: paint(33), green: paint(32), dim: paint(2), bold: paint(1), cyan: paint(36) };

const pct = (n: number) => `${Math.round(n * 100)}%`;
const ref = (t: LoadedTool) => `${t.server}/${t.name}`;
const pad = (s: string, n: number) => s + " ".repeat(Math.max(0, n - s.replace(/\x1b\[[0-9;]*m/g, "").length));

function sevLabel(sev: PairEvaluation["severity"]): string {
  const text = sev.toUpperCase();
  return sev === "high" ? c.red(text) : sev === "medium" ? c.yellow(text) : sev === "low" ? c.cyan(text) : c.green(text);
}

function truncate(s: string, n: number): string {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > n ? one.slice(0, n - 1) + "…" : one;
}

export function formatText(report: LintReport): string {
  const lines: string[] = [];
  lines.push(c.bold("MCP tool collision report"));
  lines.push(
    c.dim(
      `${report.toolCount} tools from ${report.servers.length} servers (${report.servers.join(", ")}) · ` +
        `${report.candidates.length} look-alike pairs · provider: ${report.provider}`,
    ),
  );
  lines.push("");

  if (report.candidates.length === 0) {
    lines.push(c.green("No look-alike tools found. Nothing to probe."));
    return lines.join("\n");
  }

  if (report.evaluations.length === 0) {
    lines.push(`${pad("STATIC", 8)}${pad("SHARED TERMS", 34)}PAIR`);
    for (const p of report.candidates) {
      lines.push(`${pad(p.score.toFixed(2), 8)}${pad(truncate(p.signals.sharedTerms.join(", "), 32), 34)}${ref(p.a)}  ↔  ${ref(p.b)}`);
    }
    lines.push("");
    lines.push(c.dim("Static scan only. Run without --static to measure how often a model actually confuses these."));
    return lines.join("\n");
  }

  lines.push(`${pad("SEVERITY", 10)}${pad("SWAPPED", 9)}${pad("CORRECT", 9)}${pad("OTHER", 7)}${pad("STATIC", 8)}PAIR`);
  for (const ev of report.evaluations) {
    lines.push(
      `${pad(sevLabel(ev.severity), 10)}${pad(pct(ev.confusionRate), 9)}${pad(pct(ev.accuracy), 9)}` +
        `${pad(pct(ev.elsewhere / (ev.probes.length || 1)), 7)}${pad(ev.pair.score.toFixed(2), 8)}${ref(ev.pair.a)}  ↔  ${ref(ev.pair.b)}`,
    );
  }
  lines.push(c.dim("SWAPPED: sent to the other tool in the pair · OTHER: sent to a third tool or none"));

  const notable = report.evaluations.filter((e) => e.severity === "high" || e.severity === "medium");
  for (const ev of notable) {
    const { a, b } = ev.pair;
    lines.push("");
    lines.push(c.bold(`${ref(a)}  ↔  ${ref(b)}`));
    lines.push(
      `  ${ev.aToB}/${ev.probes.filter((p) => p.intended === a.id).length} meant for ${a.name} went to ${b.server}/${b.name}; ` +
        `${ev.bToA}/${ev.probes.filter((p) => p.intended === b.id).length} meant for ${b.name} went to ${a.server}/${a.name}` +
        (ev.elsewhere ? `; ${ev.elsewhere} went to another tool or none` : ""),
    );
    if (ev.pair.signals.sharedTerms.length) lines.push(c.dim(`  overlapping terms: ${ev.pair.signals.sharedTerms.join(", ")}`));
    const misses = ev.probes.filter((p) => p.chosen !== p.intended).slice(0, 3);
    for (const m of misses) {
      lines.push(`  ${c.red("✗")} "${truncate(m.prompt, 90)}"`);
      lines.push(c.dim(`      wanted ${m.intended}, got ${m.chosen ?? "no tool"}`));
    }
    if (ev.rewrite) {
      lines.push(`  ${c.green("Suggested descriptions")}${ev.rewrite.rationale ? c.dim(` — ${ev.rewrite.rationale}`) : ""}`);
      for (const [id, d] of Object.entries(ev.rewrite.descriptions)) lines.push(`    ${c.cyan(id)}: ${d}`);
      if (ev.rewrite.after) {
        lines.push(
          `  Re-tested: confusion ${pct(ev.confusionRate)} → ${c.bold(pct(ev.rewrite.after.confusionRate))}, ` +
            `correct ${pct(ev.accuracy)} → ${c.bold(pct(ev.rewrite.after.accuracy))}`,
        );
      }
    }
  }

  if (report.provider.startsWith("offline")) {
    lines.push("");
    lines.push(
      c.dim(
        "Offline mode uses a lexical stand-in for a model. Set ANTHROPIC_API_KEY or OPENAI_API_KEY (or OPENAI_BASE_URL for Ollama) for real numbers and rewrite suggestions.",
      ),
    );
  }
  return lines.join("\n");
}

const slimTool = (t: LoadedTool) => ({ id: t.id, server: t.server, name: t.name, description: t.description });
const slimPair = (p: CandidatePair) => ({ ...p, a: slimTool(p.a), b: slimTool(p.b) });

export function toJson(report: LintReport): string {
  return JSON.stringify(
    {
      ...report,
      candidates: report.candidates.map(slimPair),
      evaluations: report.evaluations.map((e) => ({ ...e, pair: slimPair(e.pair) })),
    },
    null,
    2,
  );
}

const mdEscape = (s: string) => s.replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();

export function toMarkdown(report: LintReport): string {
  const out: string[] = [];
  out.push(`# MCP tool collision report`, "");
  out.push(
    `Generated ${report.generatedAt} · ${report.toolCount} tools from ${report.servers.length} servers · provider: \`${report.provider}\``,
    "",
  );
  if (report.evaluations.length === 0) {
    out.push("| Static score | Tool A | Tool B | Shared terms |", "|---|---|---|---|");
    for (const p of report.candidates) {
      out.push(`| ${p.score.toFixed(2)} | \`${ref(p.a)}\` | \`${ref(p.b)}\` | ${p.signals.sharedTerms.join(", ")} |`);
    }
    return out.join("\n") + "\n";
  }
  out.push("| Severity | Swapped | Correct | Other | Static | Tool A | Tool B |", "|---|---|---|---|---|---|---|");
  for (const ev of report.evaluations) {
    out.push(
      `| ${ev.severity} | ${pct(ev.confusionRate)} | ${pct(ev.accuracy)} | ${pct(ev.elsewhere / (ev.probes.length || 1))} | ${ev.pair.score.toFixed(2)} | \`${ref(ev.pair.a)}\` | \`${ref(ev.pair.b)}\` |`,
    );
  }
  out.push("", "_Swapped: sent to the other tool in the pair. Other: sent to a third tool or none._");
  for (const ev of report.evaluations.filter((e) => e.severity !== "none")) {
    out.push("", `## \`${ref(ev.pair.a)}\` ↔ \`${ref(ev.pair.b)}\``, "");
    out.push("| Prompt | Intended | Chosen |", "|---|---|---|");
    for (const p of ev.probes) {
      const mark = p.chosen === p.intended ? "✓" : "✗";
      out.push(`| ${mark} ${mdEscape(p.prompt)} | \`${p.intended}\` | \`${p.chosen ?? "none"}\` |`);
    }
    if (ev.rewrite) {
      out.push("", "**Suggested descriptions**", "");
      if (ev.rewrite.rationale) out.push(`_${ev.rewrite.rationale}_`, "");
      for (const [id, d] of Object.entries(ev.rewrite.descriptions)) out.push(`- \`${id}\`: ${d}`);
      if (ev.rewrite.after) {
        out.push(
          "",
          `Re-tested with these descriptions: confusion ${pct(ev.confusionRate)} → ${pct(ev.rewrite.after.confusionRate)}, correct ${pct(ev.accuracy)} → ${pct(ev.rewrite.after.accuracy)}.`,
        );
      }
    }
  }
  return out.join("\n") + "\n";
}
