import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { parseIssueRef } from "./github.js";
import { investigateGithubIssue } from "./service.js";

const MAX_BODY_BYTES = 64 * 1024;
const MAX_CONCURRENT = 2;
const ISSUE_IN_TEXT = /(?:https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9._-]+\/issues\/\d+|[A-Za-z0-9-]+\/[A-Za-z0-9._-]+#\d+)/;

export interface A2AOptions {
  port: number;
  host?: string;
  /** Whether requests may send redacted text to the configured model provider. */
  allowUpload: boolean;
}

export function buildAgentCard(baseUrl: string, allowUpload: boolean) {
  return {
    protocolVersion: "0.3.0",
    name: "Issue Reproduction Assistant",
    description:
      "Turns a GitHub issue into an evidence-backed reproduction brief: likely code locations, missing information, reproduction steps, and a draft failing test. Read-only; never executes repository code.",
    url: baseUrl,
    version: "0.2.0",
    preferredTransport: "JSONRPC",
    capabilities: { streaming: false, pushNotifications: false },
    defaultInputModes: ["text/plain"],
    defaultOutputModes: ["text/markdown", "application/json"],
    skills: [
      {
        id: "investigate-github-issue",
        name: "Investigate GitHub issue",
        description: `Send a message containing owner/repo#123 or an issue URL. Mode: ${allowUpload ? "model-assisted" : "offline evidence-only"}.`,
        tags: ["triage", "bug-reproduction", "github"],
        examples: ["gdgcblr/open-source-agents#1"],
      },
    ],
  };
}

function rpcError(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

async function readBody(request: IncomingMessage): Promise<string> {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY_BYTES) {
      throw new Error("Request body too large.");
    }
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function send(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

export function createA2AServer(options: A2AOptions): Server {
  let inFlight = 0;

  return createServer(async (request, response) => {
    const host = options.host ?? "127.0.0.1";
    const baseUrl = `http://${host}:${options.port}/`;
    const url = new URL(request.url ?? "/", baseUrl);

    if (request.method === "GET" && (url.pathname === "/.well-known/agent-card.json" || url.pathname === "/.well-known/agent.json")) {
      return send(response, 200, buildAgentCard(baseUrl, options.allowUpload));
    }
    if (request.method !== "POST" || url.pathname !== "/") {
      return send(response, 404, { error: "Not found" });
    }

    let id: unknown = null;
    try {
      const rpc = JSON.parse(await readBody(request)) as { id?: unknown; method?: string; params?: any };
      id = rpc.id;
      if (rpc.method !== "message/send") {
        return send(response, 200, rpcError(id, -32601, `Method not supported: ${String(rpc.method)}. Use message/send.`));
      }

      const parts: Array<{ kind?: string; text?: string }> = rpc.params?.message?.parts ?? [];
      const userText = parts.filter((part) => part.kind === "text" && typeof part.text === "string").map((part) => part.text).join("\n");
      const issueRef = ISSUE_IN_TEXT.exec(userText)?.[0];
      if (!issueRef) {
        return send(response, 200, rpcError(id, -32602, "Message must include a GitHub issue reference such as owner/repo#123."));
      }
      parseIssueRef(issueRef);

      if (inFlight >= MAX_CONCURRENT) {
        return send(response, 200, rpcError(id, -32000, "Agent is busy; retry shortly."));
      }

      inFlight += 1;
      try {
        const result = await investigateGithubIssue({ issue: issueRef, allowUpload: options.allowUpload });
        return send(response, 200, {
          jsonrpc: "2.0",
          id,
          result: {
            kind: "message",
            role: "agent",
            messageId: randomUUID(),
            parts: [
              { kind: "text", text: result.markdown },
              {
                kind: "data",
                data: {
                  mode: result.investigation.mode,
                  likelyAreas: result.investigation.report.likelyAreas,
                  questionsForReporter: result.investigation.report.questionsForReporter,
                },
              },
            ],
          },
        });
      } finally {
        inFlight -= 1;
      }
    } catch (error) {
      return send(response, 200, rpcError(id, -32603, error instanceof Error ? error.message : "Internal error"));
    }
  });
}
