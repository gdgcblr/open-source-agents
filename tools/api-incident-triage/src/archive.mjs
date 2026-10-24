/**
 * Closed-case archive (disk). Open cases stay in RAM only (see sessions.mjs).
 *
 * Layout:
 *   reports/cases/<incident_id>.json   — structured case (triage + timeline)
 *   reports/cases/<incident_id>.md     — human report
 *
 * Override directory with STACKSENTRY_CASES_DIR.
 */
import { mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_CASES_DIR = join(__dirname, "..", "reports", "cases");

export function casesDir() {
  return process.env.STACKSENTRY_CASES_DIR || DEFAULT_CASES_DIR;
}

/**
 * @param {object} session full in-memory session
 * @param {string} reportMarkdown
 */
export async function archiveClosedCase(session, reportMarkdown) {
  const dir = casesDir();
  await mkdir(dir, { recursive: true });

  const record = {
    id: session.id,
    title: session.title,
    status: "closed",
    createdAt: session.createdAt,
    closedAt: session.closedAt,
    notes: session.notes,
    events: session.events,
    latest: session.latest
      ? {
          category: session.latest.category,
          title: session.latest.title,
          evidence: session.latest.evidence,
          confidence: session.latest.confidence,
          severity: session.latest.severity,
          riskScore: session.latest.riskScore,
          blastRadius: session.latest.blastRadius,
          ownerHint: session.latest.ownerHint,
          summary: session.latest.summary,
          secondary: session.latest.secondary,
          nextSteps: session.latest.nextSteps,
          playbook: session.latest.playbook,
          evidenceSnippets: session.latest.evidenceSnippets,
        }
      : null,
    archivedAt: new Date().toISOString(),
    storage: {
      kind: "closed-archive",
      jsonPath: join(dir, `${session.id}.json`),
      mdPath: join(dir, `${session.id}.md`),
      note: "Open sessions are RAM-only. Only closed cases are written here.",
    },
  };

  const jsonPath = join(dir, `${session.id}.json`);
  const mdPath = join(dir, `${session.id}.md`);
  const md = `${reportMarkdown}\n\n---\n\n_Archived on disk at \`${mdPath}\`. Open sessions remain RAM-only._\n`;

  await writeFile(jsonPath, JSON.stringify(record, null, 2), "utf8");
  await writeFile(mdPath, md, "utf8");

  const [jsonStat, mdStat] = await Promise.all([stat(jsonPath), stat(mdPath)]);
  return {
    id: session.id,
    jsonPath,
    mdPath,
    bytes: jsonStat.size + mdStat.size,
    archivedAt: record.archivedAt,
  };
}

export async function listSavedCases() {
  const dir = casesDir();
  let names;
  try {
    names = await readdir(dir);
  } catch (err) {
    if (err && err.code === "ENOENT") return [];
    throw err;
  }

  const ids = [...new Set(names.filter((n) => n.endsWith(".json")).map((n) => n.replace(/\.json$/, "")))];
  const out = [];
  for (const id of ids) {
    try {
      const record = await loadSavedCase(id);
      const jsonPath = join(dir, `${id}.json`);
      const mdPath = join(dir, `${id}.md`);
      let bytes = 0;
      try {
        bytes += (await stat(jsonPath)).size;
      } catch {
        /* missing */
      }
      try {
        bytes += (await stat(mdPath)).size;
      } catch {
        /* missing */
      }
      out.push({
        id: record.id,
        title: record.title,
        status: record.status,
        createdAt: record.createdAt,
        closedAt: record.closedAt,
        archivedAt: record.archivedAt,
        latestCategory: record.latest?.category ?? null,
        latestRiskScore: record.latest?.riskScore ?? null,
        eventCount: record.events?.length ?? 0,
        bytes,
        jsonPath,
        mdPath,
      });
    } catch {
      // skip corrupt
    }
  }
  return out.sort((a, b) => String(b.closedAt || "").localeCompare(String(a.closedAt || "")));
}

/**
 * @param {string} id
 */
export async function loadSavedCase(id) {
  const jsonPath = join(casesDir(), `${id}.json`);
  const raw = await readFile(jsonPath, "utf8");
  return JSON.parse(raw);
}

/**
 * @param {string} id
 */
export async function loadSavedCaseMarkdown(id) {
  const mdPath = join(casesDir(), `${id}.md`);
  return readFile(mdPath, "utf8");
}

/**
 * @param {string} id
 */
export async function deleteSavedCase(id) {
  const dir = casesDir();
  const jsonPath = join(dir, `${id}.json`);
  const mdPath = join(dir, `${id}.md`);
  let removed = 0;
  for (const p of [jsonPath, mdPath]) {
    try {
      await rm(p, { force: true });
      removed += 1;
    } catch {
      /* ignore */
    }
  }
  if (removed === 0) throw new Error(`No archived case found for id: ${id}`);
  return { id, removedFiles: removed };
}

/**
 * Delete all archived cases under casesDir().
 */
export async function clearSavedCases() {
  const listed = await listSavedCases();
  let removed = 0;
  let bytesFreed = 0;
  for (const item of listed) {
    bytesFreed += item.bytes || 0;
    await deleteSavedCase(item.id);
    removed += 1;
  }
  return { removed, bytesFreed, casesDir: casesDir() };
}

export async function archiveStats() {
  const listed = await listSavedCases();
  const totalBytes = listed.reduce((sum, c) => sum + (c.bytes || 0), 0);
  return {
    casesDir: casesDir(),
    count: listed.length,
    totalBytes,
    totalKB: Math.round((totalBytes / 1024) * 10) / 10,
    mapping: "incident_id → reports/cases/<id>.json + <id>.md",
    openSessions: "RAM Map only (cleared when MCP process exits)",
    closedSessions: "Disk until delete_saved_case / clear_saved_cases / manual delete",
  };
}
