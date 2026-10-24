export type Confidence = "low" | "medium" | "high";

export interface LikelyArea {
  path: string;
  reason: string;
  confidence: Confidence;
}

export interface ReproductionTest {
  suggestedPath: string;
  framework: string;
  code: string;
}

export interface ReproductionReport {
  summary: string;
  severity: "low" | "medium" | "high" | "unknown";
  likelyAreas: LikelyArea[];
  hypotheses: string[];
  questionsForReporter: string[];
  reproductionSteps: string[];
  candidateTests: string[];
  confirmationCriteria: string[];
  reproductionTest?: ReproductionTest;
}

const CONFIDENCES = new Set<Confidence>(["low", "medium", "high"]);

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string" && v.trim() !== "").map((v) => v.trim()) : [];
}

/** Extract and validate a JSON report from possibly fenced model output. */
export function parseReport(raw: string): ReproductionReport {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(raw);
  const candidate = (fenced?.[1] ?? raw).trim();
  const start = candidate.indexOf("{");
  const end = candidate.lastIndexOf("}");
  if (start === -1 || end <= start) {
    throw new Error("Model response did not contain a JSON object.");
  }

  const data = JSON.parse(candidate.slice(start, end + 1)) as Record<string, unknown>;
  if (typeof data.summary !== "string" || !data.summary.trim()) {
    throw new Error("Model response is missing a summary.");
  }

  const areas = Array.isArray(data.likelyAreas) ? data.likelyAreas : [];
  const test = data.reproductionTest as Record<string, unknown> | undefined;

  return {
    summary: data.summary.trim(),
    severity: ["low", "medium", "high"].includes(String(data.severity)) ? (data.severity as "low" | "medium" | "high") : "unknown",
    likelyAreas: areas
      .filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null)
      .map((a) => ({
        path: String(a.path ?? "").trim(),
        reason: String(a.reason ?? "").trim(),
        confidence: CONFIDENCES.has(a.confidence as Confidence) ? (a.confidence as Confidence) : "low",
      }))
      .filter((a) => a.path),
    hypotheses: stringList(data.hypotheses),
    questionsForReporter: stringList(data.questionsForReporter),
    reproductionSteps: stringList(data.reproductionSteps),
    candidateTests: stringList(data.candidateTests),
    confirmationCriteria: stringList(data.confirmationCriteria),
    reproductionTest:
      test && typeof test.code === "string" && test.code.trim()
        ? {
            suggestedPath: String(test.suggestedPath ?? "reproduction.test"),
            framework: String(test.framework ?? "unknown"),
            code: test.code,
          }
        : undefined,
  };
}

function bullets(items: string[], numbered = false): string {
  return items.length ? items.map((item, i) => `${numbered ? `${i + 1}.` : "-"} ${item}`).join("\n") : "_None identified._";
}

export function renderReportMarkdown(report: ReproductionReport, banner?: string): string {
  const sections = [
    "# Issue reproduction brief",
    banner ? `> ${banner}` : "",
    `## Summary\n${report.summary}\n\n**Estimated severity:** ${report.severity}`,
    `## Likely areas\n${
      report.likelyAreas.length
        ? report.likelyAreas.map((a) => `- \`${a.path}\` (${a.confidence}) — ${a.reason}`).join("\n")
        : "_No code location could be identified._"
    }`,
    `## Hypotheses\n${bullets(report.hypotheses)}`,
    `## Questions for the reporter\n${bullets(report.questionsForReporter)}`,
    `## Reproduction steps (unverified)\n${bullets(report.reproductionSteps, true)}`,
    `## Candidate tests and files to inspect\n${bullets(report.candidateTests)}`,
    `## What would confirm or rule this out\n${bullets(report.confirmationCriteria)}`,
  ];

  if (report.reproductionTest) {
    const { suggestedPath, framework, code } = report.reproductionTest;
    sections.push(
      `## Draft failing test (not executed)\nSuggested file: \`${suggestedPath}\` · framework: ${framework}\n\n\`\`\`\n${code}\n\`\`\`\nReview before use; it is a starting point, not a verified reproduction.`,
    );
  }

  return sections.filter(Boolean).join("\n\n");
}
