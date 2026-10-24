/**
 * Incident sessions — model C:
 *   OPEN  → RAM Map only (cleared when MCP process exits)
 *   CLOSED → archived under reports/cases/ then removed from RAM
 */

import { archiveClosedCase, loadSavedCase, loadSavedCaseMarkdown } from "./archive.mjs";
import { compareTriages, localTriage, redactSecrets } from "./core.mjs";
import { formatMarkdownReport } from "./report.mjs";

/** @typedef {{ id: string, title: string, status: "open" | "closed", createdAt: string, closedAt?: string, notes: { at: string, text: string }[], events: object[], latest: object | null }} IncidentSession */

/** @type {Map<string, IncidentSession>} */
const sessions = new Map();

function now() {
  return new Date().toISOString();
}

function newId() {
  return `inc_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * @param {{ title?: string }} [opts]
 */
export function startIncident(opts = {}) {
  const id = newId();
  /** @type {IncidentSession} */
  const session = {
    id,
    title: opts.title?.trim() || "Untitled incident",
    status: "open",
    createdAt: now(),
    notes: [],
    events: [],
    latest: null,
  };
  sessions.set(id, session);
  return snapshot(session);
}

/**
 * Open RAM session, or closed archive on disk.
 * @param {string} id
 */
export async function getIncident(id) {
  const session = sessions.get(id);
  if (session) {
    return { source: "ram", incident: snapshot(session) };
  }
  try {
    const archived = await loadSavedCase(id);
    return { source: "disk", incident: archived };
  } catch {
    throw new Error(`Unknown incident id: ${id} (not in RAM and not in closed archive)`);
  }
}

/**
 * Open sessions in RAM only.
 */
export function listIncidents() {
  return [...sessions.values()]
    .filter((s) => s.status === "open")
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map((s) => ({
      id: s.id,
      title: s.title,
      status: s.status,
      createdAt: s.createdAt,
      eventCount: s.events.length,
      latestCategory: s.latest?.category ?? null,
      latestRiskScore: s.latest?.riskScore ?? null,
      storage: "ram",
    }));
}

/**
 * @param {string} id
 * @param {string} text
 * @param {{ source?: string }} [meta]
 */
export function triageIntoIncident(id, text, meta = {}) {
  const session = requireOpen(id);
  const sanitized = redactSecrets(text);
  const result = localTriage(sanitized);
  const event = {
    type: "triage",
    at: now(),
    source: meta.source || "triage_log",
    category: result.category,
    riskScore: result.riskScore,
    severity: result.severity,
    confidence: result.confidence,
    summary: result.summary,
    secondary: result.secondary,
  };
  session.events.push(event);
  session.latest = result;
  return {
    incident: snapshot(session),
    result,
    suggested_tool_next: suggestNext(result),
    summary_for_human: [
      `Primary: ${result.category} (score ${result.riskScore}/100, ${result.confidence} confidence)`,
      `Blast radius: ${result.blastRadius}`,
      result.secondary?.length
        ? `Also seen: ${result.secondary.map((s) => s.category).join(", ")}`
        : "No secondary signals",
    ],
  };
}

/**
 * @param {string} id
 * @param {string} note
 */
export function addIncidentNote(id, note) {
  const session = requireOpen(id);
  const entry = { at: now(), text: String(note) };
  session.notes.push(entry);
  session.events.push({ type: "note", at: entry.at, text: entry.text });
  return snapshot(session);
}

/**
 * @param {string} id
 * @param {string} before
 * @param {string} after
 */
export function compareIntoIncident(id, before, after) {
  const session = requireOpen(id);
  const left = localTriage(redactSecrets(before));
  const right = localTriage(redactSecrets(after));
  const comparison = compareTriages(left, right);
  const event = {
    type: "compare",
    at: now(),
    outcome: comparison.outcome,
    before: comparison.before,
    after: comparison.after,
    narrative: comparison.narrative,
  };
  session.events.push(event);
  session.latest = right;
  return { incident: snapshot(session), comparison };
}

/**
 * Close → write disk archive → drop from RAM.
 * @param {string} id
 */
export async function closeIncident(id) {
  const session = sessions.get(id);
  if (!session) {
    // Already archived?
    try {
      const archived = await loadSavedCase(id);
      const md = await loadSavedCaseMarkdown(id);
      return {
        incident: archived,
        reportMarkdown: md,
        archive: { id, alreadyArchived: true },
        storage: "disk",
      };
    } catch {
      throw new Error(`Unknown incident id: ${id}`);
    }
  }

  if (session.status === "closed") {
    // Should not linger in RAM under model C, but handle gracefully.
    const reportMarkdown = buildCaseReport(session);
    const archive = await archiveClosedCase(session, reportMarkdown);
    sessions.delete(id);
    return { incident: snapshot(session), reportMarkdown, archive, storage: "disk" };
  }

  session.status = "closed";
  session.closedAt = now();
  session.events.push({ type: "closed", at: session.closedAt });
  const reportMarkdown = buildCaseReport(session);
  const archive = await archiveClosedCase(session, reportMarkdown);
  const view = snapshot(session);
  sessions.delete(id);
  return {
    incident: view,
    reportMarkdown,
    archive,
    storage: "disk",
    summary_for_human: [
      `Closed ${id} and archived to disk (${archive.bytes} bytes).`,
      `RAM copy removed. Reload later with load_saved_case.`,
      `Paths: ${archive.mdPath}`,
    ],
  };
}

/**
 * @param {object} result
 */
export function suggestNext(result) {
  const next = ["get_playbook", "make_incident_report"];
  if (result.secondary?.length) next.unshift("compare_logs");
  if (result.category !== "unknown") next.push("lab_boom");
  return next;
}

/**
 * @param {string} id
 * @returns {IncidentSession}
 */
function requireOpen(id) {
  const session = sessions.get(id);
  if (!session) throw new Error(`Unknown open incident id: ${id} (closed cases are on disk — use load_saved_case)`);
  if (session.status !== "open") throw new Error(`Incident ${id} is already closed`);
  return session;
}

/** @param {IncidentSession} session */
function snapshot(session) {
  return structuredClone({
    id: session.id,
    title: session.title,
    status: session.status,
    createdAt: session.createdAt,
    closedAt: session.closedAt,
    notes: session.notes,
    events: session.events,
    latestCategory: session.latest?.category ?? null,
    latestRiskScore: session.latest?.riskScore ?? null,
    latestSummary: session.latest?.summary ?? null,
  });
}

/** @param {IncidentSession} session */
function buildCaseReport(session) {
  const lines = [
    `# StackSentry incident case`,
    ``,
    `| Field | Value |`,
    `| --- | --- |`,
    `| Case id | \`${session.id}\` |`,
    `| Title | ${session.title} |`,
    `| Status | ${session.status} |`,
    `| Opened | ${session.createdAt} |`,
    `| Closed | ${session.closedAt || "—"} |`,
    `| Events | ${session.events.length} |`,
    `| Storage model | Open=RAM · Closed=disk archive |`,
    ``,
  ];

  if (session.latest) {
    lines.push(
      `## Latest triage`,
      ``,
      formatMarkdownReport(session.latest, { source: `incident:${session.id}` }),
    );
  } else {
    lines.push(`## Latest triage`, ``, `_No triage events yet._`, ``);
  }

  if (session.notes.length) {
    lines.push(`## Notes`, ``);
    for (const n of session.notes) {
      lines.push(`- (${n.at}) ${n.text}`);
    }
    lines.push(``);
  }

  lines.push(`## Timeline`, ``);
  for (const ev of session.events) {
    if (ev.type === "triage") {
      lines.push(`- **${ev.at}** triage → \`${ev.category}\` score ${ev.riskScore} (${ev.source})`);
    } else if (ev.type === "compare") {
      lines.push(`- **${ev.at}** compare → ${ev.outcome}: ${ev.before.category} → ${ev.after.category}`);
    } else if (ev.type === "note") {
      lines.push(`- **${ev.at}** note: ${ev.text}`);
    } else if (ev.type === "lab_boom") {
      lines.push(`- **${ev.at}** lab boom \`${ev.route}\` → \`${ev.category}\``);
    } else if (ev.type === "closed") {
      lines.push(`- **${ev.at}** closed`);
    } else {
      lines.push(`- **${ev.at}** ${ev.type}`);
    }
  }
  lines.push(
    ``,
    `_Closed cases are archived under reports/cases/. Raw unredacted input logs are not stored — only triage results, notes, and timeline._`,
    ``,
  );
  return lines.join("\n");
}

/**
 * @param {string} id
 * @param {{ route: string, result: object, httpStatus: number }} boom
 */
export function attachLabBoom(id, boom) {
  const session = requireOpen(id);
  session.events.push({
    type: "lab_boom",
    at: now(),
    route: boom.route,
    httpStatus: boom.httpStatus,
    category: boom.result.category,
    riskScore: boom.result.riskScore,
    summary: boom.result.summary,
  });
  session.latest = boom.result;
  return snapshot(session);
}

/** Open RAM count (tests / stats) */
export function openSessionCount() {
  return [...sessions.values()].filter((s) => s.status === "open").length;
}

/** Test helper */
export function _resetSessionsForTests() {
  sessions.clear();
}
