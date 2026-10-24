/**
 * StackSentry MCP server (stdio) — offline triage + incident sessions + Failure Lab.
 *
 * Tools: triage, sessions, lab control, playbooks, reports
 * Resources: playbooks + example logs
 * Prompts: on-call triage, compare deploy, lab investigation
 */
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { compareTriages, localTriage, redactSecrets } from "./core.mjs";
import { LAB_ROUTES, labBoom, labScenarios, labStart, labStatus } from "./lab-client.mjs";
import { getPlaybook, PLAYBOOKS } from "./playbooks.mjs";
import { formatMarkdownReport } from "./report.mjs";
import {
  archiveStats,
  clearSavedCases,
  deleteSavedCase,
  listSavedCases,
  loadSavedCase,
  loadSavedCaseMarkdown,
} from "./archive.mjs";
import {
  addIncidentNote,
  attachLabBoom,
  closeIncident,
  compareIntoIncident,
  getIncident,
  listIncidents,
  startIncident,
  suggestNext,
  triageIntoIncident,
} from "./sessions.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const EXAMPLES = join(ROOT, "examples");

const server = new McpServer({
  name: "stacksentry",
  version: "0.2.0",
});

function asText(payload) {
  return {
    content: [
      {
        type: "text",
        text: typeof payload === "string" ? payload : JSON.stringify(payload, null, 2),
      },
    ],
  };
}

function triageEnvelope(result, extra = {}) {
  return {
    note: "Offline heuristic triage. Redaction is best-effort. Not a proven root cause.",
    result,
    summary_for_human: [
      `Primary: ${result.category} (score ${result.riskScore}/100, ${result.confidence})`,
      `Blast radius: ${result.blastRadius}`,
      `Owner hint: ${result.ownerHint}`,
    ],
    confidence_reason: result.evidence,
    suggested_tool_next: suggestNext(result),
    ...extra,
  };
}

// ─── Core tools ─────────────────────────────────────────────────────────────

server.registerTool(
  "triage_log",
  {
    description:
      "Redact secrets locally and run multi-signal StackSentry triage. Optionally attach to an open incident session.",
    inputSchema: {
      text: z.string().describe("Log excerpt or error text"),
      incident_id: z.string().optional().describe("Open incident id from start_incident"),
    },
  },
  async ({ text, incident_id }) => {
    if (incident_id) {
      const attached = triageIntoIncident(incident_id, text, { source: "triage_log" });
      return asText({
        note: "Attached to incident session (in-memory).",
        ...attached,
        confidence_reason: attached.result.evidence,
      });
    }
    const result = localTriage(redactSecrets(text));
    return asText(triageEnvelope(result));
  },
);

server.registerTool(
  "redact_secrets",
  {
    description: "Best-effort local redaction only. Does not upload or triage.",
    inputSchema: { text: z.string() },
  },
  async ({ text }) => asText({ sanitized: redactSecrets(text) }),
);

server.registerTool(
  "compare_logs",
  {
    description: "Compare two log excerpts after local triage. Optionally record on an incident.",
    inputSchema: {
      before: z.string(),
      after: z.string(),
      incident_id: z.string().optional(),
    },
  },
  async ({ before, after, incident_id }) => {
    if (incident_id) {
      return asText(compareIntoIncident(incident_id, before, after));
    }
    const left = localTriage(redactSecrets(before));
    const right = localTriage(redactSecrets(after));
    return asText({
      comparison: compareTriages(left, right),
      before: { category: left.category, riskScore: left.riskScore },
      after: { category: right.category, riskScore: right.riskScore },
      suggested_tool_next: ["get_playbook", "make_incident_report", "close_incident"],
    });
  },
);

server.registerTool(
  "get_playbook",
  {
    description: "Playbook, blast radius, owner hint, and base score for a category.",
    inputSchema: {
      category: z.string().describe(`e.g. ${Object.keys(PLAYBOOKS).slice(0, 6).join(", ")}`),
    },
  },
  async ({ category }) => asText(getPlaybook(category)),
);

server.registerTool(
  "make_incident_report",
  {
    description: "Triage text and return a markdown incident report.",
    inputSchema: {
      text: z.string(),
      source: z.string().optional(),
    },
  },
  async ({ text, source }) => {
    const result = localTriage(redactSecrets(text));
    return {
      content: [
        {
          type: "text",
          text: formatMarkdownReport(result, { source: source || "mcp:make_incident_report" }),
        },
      ],
    };
  },
);

// ─── Incident sessions ──────────────────────────────────────────────────────

server.registerTool(
  "start_incident",
  {
    description:
      "Open a RAM-only incident case (not on disk until close_incident). Returns incident_id.",
    inputSchema: {
      title: z.string().optional().describe("Short case title"),
    },
  },
  async ({ title }) =>
    asText({
      incident: startIncident({ title }),
      storage: "ram",
      suggested_tool_next: ["triage_log", "lab_boom", "add_incident_note", "close_incident"],
      summary_for_human: [
        "Opened RAM session. Survives tool calls until MCP restarts.",
        "On close_incident it is archived under reports/cases/ and removed from RAM.",
      ],
    }),
);

server.registerTool(
  "list_incidents",
  {
    description: "List OPEN incidents currently in RAM (not the disk archive).",
  },
  async () => asText({ openIncidents: listIncidents(), storage: "ram" }),
);

server.registerTool(
  "get_incident",
  {
    description: "Fetch an incident from RAM (open) or disk archive (closed).",
    inputSchema: { incident_id: z.string() },
  },
  async ({ incident_id }) => asText(await getIncident(incident_id)),
);

server.registerTool(
  "add_incident_note",
  {
    description: "Add an investigator note to an OPEN RAM incident.",
    inputSchema: {
      incident_id: z.string(),
      note: z.string(),
    },
  },
  async ({ incident_id, note }) => asText({ incident: addIncidentNote(incident_id, note) }),
);

server.registerTool(
  "close_incident",
  {
    description:
      "Close an open incident: write reports/cases/<id>.json+.md, return markdown, remove from RAM.",
    inputSchema: { incident_id: z.string() },
  },
  async ({ incident_id }) => {
    const closed = await closeIncident(incident_id);
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              incident: closed.incident,
              archive: closed.archive,
              storage: closed.storage,
              summary_for_human: closed.summary_for_human,
            },
            null,
            2,
          ),
        },
        {
          type: "text",
          text: closed.reportMarkdown,
        },
      ],
    };
  },
);

server.registerTool(
  "list_saved_cases",
  {
    description: "List CLOSED cases archived on disk under reports/cases/.",
  },
  async () => asText({ savedCases: await listSavedCases(), ...(await archiveStats()) }),
);

server.registerTool(
  "load_saved_case",
  {
    description: "Load a closed archived case (JSON + markdown) by incident_id.",
    inputSchema: { incident_id: z.string() },
  },
  async ({ incident_id }) => {
    const record = await loadSavedCase(incident_id);
    const markdown = await loadSavedCaseMarkdown(incident_id);
    return {
      content: [
        { type: "text", text: JSON.stringify({ source: "disk", case: record }, null, 2) },
        { type: "text", text: markdown },
      ],
    };
  },
);

server.registerTool(
  "delete_saved_case",
  {
    description: "Delete one archived case from disk (JSON + MD).",
    inputSchema: { incident_id: z.string() },
  },
  async ({ incident_id }) => asText(await deleteSavedCase(incident_id)),
);

server.registerTool(
  "clear_saved_cases",
  {
    description: "Delete ALL archived cases from reports/cases/. Does not affect open RAM sessions.",
  },
  async () => asText(await clearSavedCases()),
);

server.registerTool(
  "archive_stats",
  {
    description: "Show archive directory, case count, and approximate disk usage.",
  },
  async () => asText(await archiveStats()),
);

// ─── Failure Lab tools ──────────────────────────────────────────────────────

server.registerTool(
  "lab_status",
  {
    description: "Check whether the local Failure Lab HTTP server is reachable.",
  },
  async () => asText(await labStatus()),
);

server.registerTool(
  "lab_scenarios",
  {
    description: "List intentional /boom/* Failure Lab routes.",
  },
  async () => asText(await labScenarios()),
);

server.registerTool(
  "lab_start",
  {
    description:
      "Start the local Failure Lab on 127.0.0.1 if it is not already running (spawns lab/server.mjs).",
  },
  async () =>
    asText({
      ...(await labStart()),
      suggested_tool_next: ["lab_boom", "lab_scenarios"],
    }),
);

server.registerTool(
  "lab_boom",
  {
    description:
      "Trigger a Failure Lab boom route, triage the synthetic response offline, optionally attach to an incident.",
    inputSchema: {
      route: z
        .string()
        .describe(`Lab route such as /boom/schema or schema. Known: ${LAB_ROUTES.join(", ")}`),
      incident_id: z.string().optional(),
    },
  },
  async ({ route, incident_id }) => {
    const boom = await labBoom(route);
    let incident = null;
    if (incident_id) {
      incident = attachLabBoom(incident_id, boom);
    }
    return asText({
      ...boom,
      incident,
      suggested_tool_next: incident_id
        ? ["get_playbook", "add_incident_note", "close_incident"]
        : ["start_incident", "get_playbook", "make_incident_report"],
    });
  },
);

// ─── Resources ──────────────────────────────────────────────────────────────

server.registerResource(
  "playbook-index",
  "stacksentry://playbooks",
  {
    title: "StackSentry playbook index",
    description: "List of incident categories with base risk scores",
    mimeType: "application/json",
  },
  async (uri) => ({
    contents: [
      {
        uri: uri.href,
        mimeType: "application/json",
        text: JSON.stringify(
          Object.entries(PLAYBOOKS).map(([category, p]) => ({
            category,
            score: p.score,
            ownerHint: p.ownerHint,
            uri: `stacksentry://playbooks/${category}`,
          })),
          null,
          2,
        ),
      },
    ],
  }),
);

server.registerResource(
  "playbook",
  new ResourceTemplate("stacksentry://playbooks/{category}", {
    list: async () => ({
      resources: Object.keys(PLAYBOOKS).map((category) => ({
        uri: `stacksentry://playbooks/${category}`,
        name: category,
        mimeType: "application/json",
      })),
    }),
  }),
  {
    title: "StackSentry playbook",
    description: "Playbook document for one category",
    mimeType: "application/json",
  },
  async (uri, variables) => {
    const category = String(variables.category || "");
    const playbook = getPlaybook(category);
    return {
      contents: [
        {
          uri: uri.href,
          mimeType: "application/json",
          text: JSON.stringify(playbook, null, 2),
        },
      ],
    };
  },
);

server.registerResource(
  "example-sample-error",
  "stacksentry://examples/sample-error.log",
  {
    title: "Sample schema-error log",
    description: "Synthetic Postgres 42P01 example",
    mimeType: "text/plain",
  },
  async (uri) => ({
    contents: [
      {
        uri: uri.href,
        mimeType: "text/plain",
        text: await readFile(join(EXAMPLES, "sample-error.log"), "utf8"),
      },
    ],
  }),
);

server.registerResource(
  "example-connection-refused",
  "stacksentry://examples/connection-refused.log",
  {
    title: "Sample connection-refused log",
    description: "Synthetic ECONNREFUSED example",
    mimeType: "text/plain",
  },
  async (uri) => ({
    contents: [
      {
        uri: uri.href,
        mimeType: "text/plain",
        text: await readFile(join(EXAMPLES, "connection-refused.log"), "utf8"),
      },
    ],
  }),
);

server.registerResource(
  "lab-routes",
  "stacksentry://lab/routes",
  {
    title: "Failure Lab routes",
    description: "Intentional boom endpoints for demos",
    mimeType: "application/json",
  },
  async (uri) => ({
    contents: [
      {
        uri: uri.href,
        mimeType: "application/json",
        text: JSON.stringify({ routes: LAB_ROUTES, how: "Call lab_start then lab_boom" }, null, 2),
      },
    ],
  }),
);

// ─── Prompts ────────────────────────────────────────────────────────────────

server.registerPrompt(
  "junior_oncall_triage",
  {
    title: "Junior on-call triage",
    description: "Guide a careful offline triage of a pasted log with StackSentry tools",
    argsSchema: {
      log_excerpt: z.string().describe("Raw log text to investigate"),
    },
  },
  ({ log_excerpt }) => ({
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text: [
            "You are helping a junior on-call engineer.",
            "Use StackSentry MCP tools only (offline). Do not invent root cause certainty.",
            "Steps:",
            "1) start_incident with a short title",
            "2) triage_log with the excerpt and incident_id",
            "3) get_playbook for the primary category",
            "4) make_incident_report or close_incident for handoff",
            "Remind that redaction is best-effort.",
            "",
            "Log excerpt:",
            "```",
            log_excerpt,
            "```",
          ].join("\n"),
        },
      },
    ],
  }),
);

server.registerPrompt(
  "compare_before_after",
  {
    title: "Before/after deploy compare",
    description: "Compare two log excerpts to see if the failure class changed",
    argsSchema: {
      before_log: z.string(),
      after_log: z.string(),
    },
  },
  ({ before_log, after_log }) => ({
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text: [
            "Compare these two logs with StackSentry compare_logs (and optionally an incident session).",
            "Explain whether the primary incident class changed and what to verify next.",
            "",
            "BEFORE:",
            "```",
            before_log,
            "```",
            "",
            "AFTER:",
            "```",
            after_log,
            "```",
          ].join("\n"),
        },
      },
    ],
  }),
);

server.registerPrompt(
  "lab_investigation",
  {
    title: "Failure Lab investigation",
    description: "Trigger a lab boom and produce a scored playbook report",
    argsSchema: {
      route: z.string().describe("Boom route short name or path, e.g. schema or /boom/refused"),
    },
  },
  ({ route }) => ({
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text: [
            "Run a StackSentry Failure Lab investigation:",
            "1) lab_status (if down, lab_start)",
            `2) lab_boom route=${route || "schema"}`,
            "3) start_incident titled for that failure",
            "4) attach by calling lab_boom again with incident_id OR triage_log the lab response",
            "5) get_playbook + close_incident",
            "Keep everything local; do not call external AI APIs for the triage itself.",
          ].join("\n"),
        },
      },
    ],
  }),
);

const transport = new StdioServerTransport();
await server.connect(transport);
