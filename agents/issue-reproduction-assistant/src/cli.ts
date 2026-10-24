#!/usr/bin/env node
import "dotenv/config";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { investigate } from "./pipeline.js";
import { redactSensitiveContent } from "./repository-context.js";
import { investigateGithubIssue, renderInvestigation, resolveProvider } from "./service.js";

const MAX_ISSUE_CHARACTERS = 20_000;

interface CliOptions {
  github?: string;
  issuePath?: string;
  repositoryPath?: string;
  allowUpload: boolean;
  json: boolean;
  outPath?: string;
  help: boolean;
}

function parseArguments(args: string[]): CliOptions {
  const options: CliOptions = { allowUpload: false, json: false, help: false };
  const value = (index: number, flag: string): string => {
    const next = args[index];
    if (!next || next.startsWith("--")) {
      throw new Error(`${flag} requires a value.`);
    }
    return next;
  };

  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    switch (argument) {
      case "--github": options.github = value(++index, argument); break;
      case "--issue": options.issuePath = value(++index, argument); break;
      case "--repo": options.repositoryPath = value(++index, argument); break;
      case "--out": options.outPath = value(++index, argument); break;
      case "--allow-upload": options.allowUpload = true; break;
      case "--offline": options.allowUpload = false; break;
      case "--json": options.json = true; break;
      case "--help":
      case "-h": options.help = true; break;
      default: throw new Error(`Unknown argument: ${argument}`);
    }
  }
  return options;
}

function printHelp(): void {
  console.log(`Issue Reproduction Assistant

Usage:
  npm start -- --github owner/repo#123 [--allow-upload]
  npm start -- --issue <bug-report.md> --repo <path> [--allow-upload]
  npm run mcp        Start the MCP server (stdio)
  npm run a2a        Start the A2A agent server

Options:
  --github <ref>     GitHub issue (owner/repo#123 or URL); the repo is shallow-cloned read-only
  --issue <path>     Local text/Markdown bug report (requires --repo)
  --repo <path>      Local repository to inspect (read-only)
  --allow-upload     Send the redacted issue + selected excerpts to the configured model.
                     Without it the agent runs offline (evidence-only; nothing leaves this machine)
  --json             Print the full investigation as JSON
  --out <path>       Write the Markdown/JSON output to a file
  --help, -h         Show this help

Configuration (env or .env):
  AI_PROVIDER        gemini (default) | ollama (local, e.g. Gemma)
  AI_MODEL           Model ID (default: gemini-2.5-flash / gemma3)
  GEMINI_API_KEY     Gemini API key
  OLLAMA_HOST        Ollama URL (default: http://localhost:11434)
  GITHUB_TOKEN       Optional; raises GitHub API rate limits`);
}

async function run(): Promise<void> {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    printHelp();
    return;
  }

  let markdown: string;
  let payload: unknown;

  if (options.github) {
    const result = await investigateGithubIssue({
      issue: options.github,
      allowUpload: options.allowUpload,
      repositoryPath: options.repositoryPath ? path.resolve(options.repositoryPath) : undefined,
    });
    markdown = result.markdown;
    payload = { issue: { ...result.issue, comments: result.issue.comments.length }, ...result.investigation };
  } else if (options.issuePath && options.repositoryPath) {
    const raw = await readFile(path.resolve(options.issuePath), "utf8");
    if (raw.length > MAX_ISSUE_CHARACTERS) {
      throw new Error(`Issue text exceeds the ${MAX_ISSUE_CHARACTERS}-character limit.`);
    }
    const issueText = redactSensitiveContent(raw);
    if (!issueText.trim()) {
      throw new Error("Issue report is empty.");
    }
    const investigation = await investigate({
      issueText,
      repositoryPath: path.resolve(options.repositoryPath),
      provider: resolveProvider(options.allowUpload),
    });
    markdown = renderInvestigation(investigation);
    payload = investigation;
  } else {
    throw new Error("Provide --github <ref>, or both --issue and --repo. Use --help for usage.");
  }

  if (!options.allowUpload) {
    console.error("Running offline (no --allow-upload): no data is sent to any model provider.");
  }

  const output = options.json ? JSON.stringify(payload, null, 2) : markdown;
  if (options.outPath) {
    await writeFile(path.resolve(options.outPath), `${output}\n`, "utf8");
    console.error(`Wrote ${options.outPath}`);
  } else {
    console.log(output);
  }
}

run().catch((error: unknown) => {
  console.error(`Error: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
