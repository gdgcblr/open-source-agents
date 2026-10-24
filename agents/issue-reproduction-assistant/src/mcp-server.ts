import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { getFileHistory } from "./git-history.js";
import { fetchGithubIssue, issueToText, parseIssueRef } from "./github.js";
import { locate } from "./localize.js";
import { investigate } from "./pipeline.js";
import { readRepositoryFiles, redactSensitiveContent } from "./repository-context.js";
import { describeMissingInformation, extractSignals } from "./signals.js";
import { investigateGithubIssue, renderInvestigation, resolveProvider } from "./service.js";

const readOnly = { readOnlyHint: true, destructiveHint: false, idempotentHint: true };

function text(content: string) {
  return { content: [{ type: "text" as const, text: content }] };
}

function failure(error: unknown) {
  return { isError: true, content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }] };
}

/** MCP server exposing the agent's building blocks as read-only tools. */
export function createMcpServer(): McpServer {
  const server = new McpServer({ name: "issue-reproduction-assistant", version: "0.2.0" });

  server.registerTool(
    "fetch_github_issue",
    {
      title: "Fetch GitHub issue",
      description: "Fetch a public GitHub issue and its comments (redacted) as text. Accepts owner/repo#123 or an issue URL.",
      inputSchema: { issue: z.string().describe("owner/repo#123 or github.com issue URL") },
      annotations: { ...readOnly, openWorldHint: true },
    },
    async ({ issue }) => {
      try {
        return text(issueToText(await fetchGithubIssue(parseIssueRef(issue))));
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "extract_issue_signals",
    {
      title: "Extract issue signals",
      description: "Extract stack frames, file paths, identifiers, error messages, versions and missing-information gaps from bug report text. Runs locally.",
      inputSchema: { issueText: z.string().max(20_000) },
      annotations: { ...readOnly, openWorldHint: false },
    },
    async ({ issueText }) => {
      const signals = extractSignals(redactSensitiveContent(issueText));
      return text(JSON.stringify({ ...signals, missingInformation: describeMissingInformation(signals) }, null, 2));
    },
  );

  server.registerTool(
    "locate_code",
    {
      title: "Locate relevant code",
      description: "Rank files in a local repository by relevance to a bug report, returning line-level evidence. Read-only; runs locally.",
      inputSchema: {
        repositoryPath: z.string().describe("Absolute path to a local repository"),
        issueText: z.string().max(20_000),
      },
      annotations: { ...readOnly, openWorldHint: false },
    },
    async ({ repositoryPath, issueText }) => {
      try {
        const files = await readRepositoryFiles(repositoryPath);
        const candidates = locate(files, extractSignals(redactSensitiveContent(issueText))).slice(0, 10);
        return text(JSON.stringify(candidates, null, 2));
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "file_history",
    {
      title: "File history",
      description: "Recent git commits touching a file inside a local repository. Read-only.",
      inputSchema: {
        repositoryPath: z.string(),
        file: z.string().describe("Path relative to the repository root"),
        limit: z.number().int().min(1).max(20).optional(),
      },
      annotations: { ...readOnly, openWorldHint: false },
    },
    async ({ repositoryPath, file, limit }) => {
      try {
        return text(JSON.stringify(await getFileHistory(repositoryPath, file, limit ?? 5), null, 2));
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "investigate_issue",
    {
      title: "Investigate issue",
      description:
        "Produce a reproduction brief for a GitHub issue (shallow read-only clone) or for supplied issue text + local repository. Offline by default; set allowUpload=true to also send redacted excerpts to the configured model provider.",
      inputSchema: {
        issue: z.string().optional().describe("owner/repo#123 or issue URL"),
        issueText: z.string().max(20_000).optional(),
        repositoryPath: z.string().optional(),
        allowUpload: z.boolean().optional().describe("Permit sending redacted text to the configured model provider"),
      },
      annotations: { ...readOnly, openWorldHint: true },
    },
    async ({ issue, issueText, repositoryPath, allowUpload }) => {
      try {
        if (issue) {
          return text((await investigateGithubIssue({ issue, allowUpload, repositoryPath })).markdown);
        }
        if (!issueText || !repositoryPath) {
          throw new Error("Provide `issue`, or both `issueText` and `repositoryPath`.");
        }
        const investigation = await investigate({
          issueText: redactSensitiveContent(issueText),
          repositoryPath,
          provider: resolveProvider(allowUpload),
        });
        return text(renderInvestigation(investigation));
      } catch (error) {
        return failure(error);
      }
    },
  );

  return server;
}
