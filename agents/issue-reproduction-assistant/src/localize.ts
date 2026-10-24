import type { ContextFile } from "./repository-context.js";
import type { IssueSignals } from "./signals.js";

export interface EvidenceLine {
  line: number;
  text: string;
  reason: string;
}

export interface CandidateLocation {
  path: string;
  score: number;
  reasons: string[];
  evidence: EvidenceLine[];
}

const MAX_EVIDENCE_PER_FILE = 6;
const GENERIC_NAMES = new Set(["index", "main", "utils", "util", "helpers", "types", "test", "tests"]);

function isTestFile(filePath: string): boolean {
  return /(^|\/)(tests?|__tests__|spec)\/|\.(test|spec)\.[a-z]+$|(^|\/)test_[^/]+\.py$|_test\.(go|py)$/i.test(filePath);
}

function pathMatches(candidate: string, wanted: string): boolean {
  const a = candidate.replace(/\\/g, "/").toLowerCase();
  const b = wanted.replace(/\\/g, "/").toLowerCase();
  return a === b || a.endsWith(`/${b}`) || b.endsWith(`/${a}`);
}

export function locate(files: ContextFile[], signals: IssueSignals): CandidateLocation[] {
  const identifiers = signals.identifiers.filter((id) => id.length >= 4);
  const keywords = new Set(signals.keywords.slice(0, 40));
  const results: CandidateLocation[] = [];

  for (const file of files) {
    const reasons: string[] = [];
    const evidence: EvidenceLine[] = [];
    let score = 0;
    const lowerPath = file.path.toLowerCase();
    const lines = file.content.split("\n");

    const frame = signals.stackFrames.find((candidate) => pathMatches(file.path, candidate.file));
    if (frame) {
      score += 30;
      reasons.push(frame.line ? `named in stack trace (line ${frame.line})` : "named in stack trace");
      if (frame.line && frame.line <= lines.length) {
        evidence.push({ line: frame.line, text: lines[frame.line - 1].trim().slice(0, 160), reason: "stack frame line" });
      }
    }

    if (signals.filePaths.some((wanted) => pathMatches(file.path, wanted))) {
      score += 15;
      reasons.push("path mentioned in the issue");
    }

    const matchedIdentifiers = new Set<string>();
    const matchedErrors = new Set<string>();
    lines.forEach((text, index) => {
      if (evidence.length >= MAX_EVIDENCE_PER_FILE) {
        return;
      }
      for (const message of signals.errorMessages) {
        const needle = message.split(":").slice(1).join(":").trim() || message;
        if (needle.length >= 8 && text.includes(needle.slice(0, 60))) {
          matchedErrors.add(message);
          evidence.push({ line: index + 1, text: text.trim().slice(0, 160), reason: "error message text" });
          return;
        }
      }
      for (const identifier of identifiers) {
        if (text.includes(identifier)) {
          matchedIdentifiers.add(identifier);
          if (evidence.length < MAX_EVIDENCE_PER_FILE) {
            evidence.push({ line: index + 1, text: text.trim().slice(0, 160), reason: `mentions ${identifier}` });
          }
          return;
        }
      }
    });

    if (matchedErrors.size > 0) {
      score += 20 * matchedErrors.size;
      reasons.push("contains the reported error text");
    }
    if (matchedIdentifiers.size > 0) {
      score += Math.min(matchedIdentifiers.size, 6) * 4;
      reasons.push(`references ${[...matchedIdentifiers].slice(0, 4).join(", ")}`);
    }

    const baseName = lowerPath.split("/").pop()?.replace(/\.[^.]+$/, "") ?? "";
    if (baseName && !GENERIC_NAMES.has(baseName) && keywords.has(baseName)) {
      score += 6;
      reasons.push(`file name matches "${baseName}"`);
    }

    if (score > 0) {
      results.push({ path: file.path, score, reasons, evidence: dedupeEvidence(evidence) });
    }
  }

  return results.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path));
}

function dedupeEvidence(evidence: EvidenceLine[]): EvidenceLine[] {
  const seen = new Set<number>();
  return evidence.filter((item) => !seen.has(item.line) && seen.add(item.line));
}

export function findExistingTests(files: ContextFile[], candidates: CandidateLocation[]): string[] {
  const stems = new Set(
    candidates.slice(0, 5).map((candidate) => candidate.path.split("/").pop()?.replace(/\.[^.]+$/, "").toLowerCase() ?? ""),
  );
  return files
    .filter((file) => isTestFile(file.path))
    .filter((file) => {
      const lower = file.path.toLowerCase();
      return [...stems].some((stem) => stem.length >= 3 && lower.includes(stem));
    })
    .map((file) => file.path)
    .slice(0, 8);
}

export function rankFiles(files: ContextFile[], signals: IssueSignals): ContextFile[] {
  const scores = new Map(locate(files, signals).map((candidate) => [candidate.path, candidate.score]));
  return [...files].sort((a, b) => {
    const diff = (scores.get(b.path) ?? 0) - (scores.get(a.path) ?? 0);
    if (diff !== 0) {
      return diff;
    }
    const aDoc = /^(readme|package\.json|pyproject\.toml|cargo\.toml|go\.mod)/i.test(a.path) ? 1 : 0;
    const bDoc = /^(readme|package\.json|pyproject\.toml|cargo\.toml|go\.mod)/i.test(b.path) ? 1 : 0;
    return bDoc - aDoc || a.path.localeCompare(b.path);
  });
}
