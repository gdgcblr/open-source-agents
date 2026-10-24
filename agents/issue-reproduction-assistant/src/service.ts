import { createProvider, readConfig } from "./config.js";
import {
  cloneRepository,
  fetchGithubIssue,
  issueToText,
  parseIssueRef,
  type GithubIssue,
} from "./github.js";
import type { ModelProvider } from "./model-provider.js";
import { investigate, type Investigation } from "./pipeline.js";
import { renderReportMarkdown } from "./report.js";

export interface GithubInvestigationRequest {
  issue: string;
  allowUpload?: boolean;
  repositoryPath?: string;
}

export interface GithubInvestigationResult {
  issue: GithubIssue;
  investigation: Investigation;
  markdown: string;
}

export function resolveProvider(allowUpload: boolean | undefined): ModelProvider | undefined {
  return allowUpload ? createProvider(readConfig()) : undefined;
}

export function renderInvestigation(
  investigation: Investigation,
  heading?: { title: string; url?: string },
): string {
  const banner =
    investigation.mode === "llm"
      ? `Generated with ${investigation.provider}/${investigation.model} from the issue text and selected repository excerpts. Hypotheses only — nothing was executed.`
      : "Offline evidence-only mode: no model was used and no data left this machine.";

  const evidence = investigation.candidates
    .slice(0, 5)
    .map((candidate) => {
      const lines = candidate.evidence
        .slice(0, 3)
        .map((item) => `  - L${item.line}: \`${item.text.replace(/`/g, "'")}\` (${item.reason})`)
        .join("\n");
      const commits = (investigation.history[candidate.path] ?? [])
        .map((commit) => `  - ${commit.hash} ${commit.date} ${commit.subject}`)
        .join("\n");
      return `- \`${candidate.path}\` — score ${candidate.score}\n${lines}${commits ? `\n  Recent commits:\n${commits}` : ""}`;
    })
    .join("\n");

  return [
    heading ? `**Issue:** ${heading.title}${heading.url ? ` — ${heading.url}` : ""}\n` : "",
    renderReportMarkdown(investigation.report, banner),
    evidence ? `## Evidence from the repository\n${evidence}` : "",
    investigation.warnings.length ? `## Warnings\n${investigation.warnings.map((w) => `- ${w}`).join("\n")}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

export async function investigateGithubIssue(
  request: GithubInvestigationRequest,
): Promise<GithubInvestigationResult> {
  const ref = parseIssueRef(request.issue);
  const provider = resolveProvider(request.allowUpload);
  const issue = await fetchGithubIssue(ref);
  const issueText = issueToText(issue);

  const cloned = request.repositoryPath ? undefined : await cloneRepository(ref);
  try {
    const investigation = await investigate({
      issueText,
      repositoryPath: request.repositoryPath ?? cloned!.path,
      provider,
    });
    return {
      issue,
      investigation,
      markdown: renderInvestigation(investigation, { title: issue.title, url: issue.url }),
    };
  } finally {
    await cloned?.cleanup();
  }
}
