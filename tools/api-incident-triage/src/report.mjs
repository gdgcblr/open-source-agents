/**
 * Build a markdown incident report from a triage result.
 * @param {object} result
 * @param {{ source?: string, generatedAt?: string }} [meta]
 */
export function formatMarkdownReport(result, meta = {}) {
  const generatedAt = meta.generatedAt ?? new Date().toISOString();
  const source = meta.source ?? "stdin/file";
  const lines = [
    `# StackSentry incident report`,
    ``,
    `| Field | Value |`,
    `| --- | --- |`,
    `| Generated | ${generatedAt} |`,
    `| Source | ${source} |`,
    `| Risk score | **${result.riskScore}/100** |`,
    `| Severity | ${result.severity} |`,
    `| Primary | \`${result.category}\` |`,
    `| Confidence | ${result.confidence} |`,
    `| Owner hint | ${result.ownerHint} |`,
    ``,
    `## Summary`,
    ``,
    result.summary,
    ``,
    `## Likely cause`,
    ``,
    result.title,
    ``,
    `## Evidence`,
    ``,
    result.evidence,
    ``,
  ];

  if (result.secondary?.length) {
    lines.push(`## Secondary signals`, ``);
    for (const s of result.secondary) {
      lines.push(`- \`${s.category}\` (${s.confidence} / ${s.severity})`);
    }
    lines.push(``);
  }

  if (result.evidenceSnippets?.length) {
    lines.push(`## Evidence snippets (sanitized)`, ``, "```text");
    for (const snippet of result.evidenceSnippets) lines.push(snippet);
    lines.push("```", ``);
  }

  lines.push(
    `## Blast radius`,
    ``,
    result.blastRadius,
    ``,
    `## Playbook`,
    ``,
  );
  for (const [i, step] of (result.playbook ?? []).entries()) {
    lines.push(`${i + 1}. ${step}`);
  }

  lines.push(
    ``,
    `## Quick verification checks`,
    ``,
  );
  for (const [i, step] of (result.nextSteps ?? []).entries()) {
    lines.push(`${i + 1}. ${step}`);
  }

  lines.push(
    ``,
    `---`,
    ``,
    `_Heuristic local report. Redaction is best-effort. Not a proven root cause._`,
    ``,
  );

  return lines.join("\n");
}
