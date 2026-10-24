export interface StackFrame {
  file: string;
  line?: number;
  symbol?: string;
}

export interface IssueSignals {
  stackFrames: StackFrame[];
  filePaths: string[];
  identifiers: string[];
  errorMessages: string[];
  versions: string[];
  codeBlocks: string[];
  hasReproSteps: boolean;
  hasExpectedActual: boolean;
  keywords: string[];
}

const FILE_EXTENSIONS =
  "ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|rb|php|cs|cpp|cc|c|h|hpp|swift|vue|svelte";
const FILE_PATH = new RegExp(
  `(?:[\\w@.-]+/)*[\\w@.-]+\\.(?:${FILE_EXTENSIONS})\\b`,
  "g",
);
const STOP_WORDS = new Set([
  "about", "after", "also", "because", "before", "being", "could", "doesn", "error",
  "expected", "from", "have", "here", "into", "issue", "just", "like", "need", "should",
  "that", "their", "there", "these", "this", "using", "version", "when", "where", "which",
  "while", "with", "would", "actual", "behavior", "behaviour", "steps", "reproduce",
  "node", "development", "production", "undefined", "null", "true", "false", "function",
  "object", "string", "number", "array", "console", "window", "internal", "module", "modules",
  "process", "async", "await", "promise", "return", "const", "class", "import", "export",
  "default", "request", "response", "properties", "reading", "cannot", "read", "type",
]);

function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

function normalizePath(rawPath: string): string {
  return rawPath.replace(/^(?:\.\/|file:\/\/)/, "").replace(/^[A-Za-z]:/, "");
}

function extractStackFrames(text: string): StackFrame[] {
  const frames: StackFrame[] = [];
  const patterns: Array<{ regex: RegExp; map: (m: RegExpExecArray) => StackFrame }> = [
    // JS/TS: at fn (path:line:col) or at path:line:col
    {
      regex: new RegExp(`at (?:(.+?) \\()?([^\\s()]+\\.(?:${FILE_EXTENSIONS})):(\\d+)(?::\\d+)?\\)?`, "g"),
      map: (m) => ({ symbol: m[1], file: normalizePath(m[2]), line: Number(m[3]) }),
    },
    // Python: File "path", line N, in fn
    {
      regex: /File "([^"]+)", line (\d+)(?:, in (\S+))?/g,
      map: (m) => ({ file: normalizePath(m[1]), line: Number(m[2]), symbol: m[3] }),
    },
    // Go / generic: path.ext:line
    {
      regex: new RegExp(`([\\w@./-]+\\.(?:go|rs|java|kt|rb|php|cs|cpp|c|h)):(\\d+)`, "g"),
      map: (m) => ({ file: normalizePath(m[1]), line: Number(m[2]) }),
    },
  ];

  for (const { regex, map } of patterns) {
    for (const match of text.matchAll(regex)) {
      frames.push(map(match as RegExpExecArray));
    }
  }

  const seen = new Set<string>();
  return frames.filter((frame) => {
    const key = `${frame.file}:${frame.line ?? ""}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function extractSignals(text: string): IssueSignals {
  const codeBlocks = [...text.matchAll(/```[^\n]*\n([\s\S]*?)```/g)].map((m) => m[1].trim());
  const stackFrames = extractStackFrames(text).filter(
    (frame) => !/node_modules|site-packages|\/usr\/lib/.test(frame.file),
  );
  const filePaths = unique(
    [...text.matchAll(FILE_PATH)]
      .map((m) => normalizePath(m[0]))
      .filter((p) => !/^(?:https?:|www\.)/.test(p) && !p.includes("node_modules")),
  );

  const backticked = [...text.matchAll(/`([^`\n]{2,80})`/g)].map((m) => m[1].trim());
  const identifiers = unique([
    ...backticked.flatMap((entry) => entry.match(/[A-Za-z_$][\w$]{2,}/g) ?? []),
    ...(text.match(/\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b|\b[a-z0-9]+(?:_[a-z0-9]+)+\b/g) ?? []),
  ]).filter((id) => !STOP_WORDS.has(id.toLowerCase())).slice(0, 40);

  const errorMessages = unique(
    [...text.matchAll(/^\s*((?:[A-Z][A-Za-z]*(?:Error|Exception)|panic|fatal|error)[:\s].{3,160})$/gim)].map((m) =>
      m[1].trim(),
    ),
  ).slice(0, 8);

  const versions = unique(
    [...text.matchAll(/\b(?:v|version\s*)?(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)\b/gi)].map((m) => m[1]),
  ).slice(0, 10);

  const keywords = unique(
    (text.toLowerCase().match(/[a-z][a-z0-9_]{3,}/g) ?? []).filter((w) => !STOP_WORDS.has(w)),
  ).slice(0, 60);

  return {
    stackFrames,
    filePaths,
    identifiers,
    errorMessages,
    versions,
    codeBlocks,
    hasReproSteps: /(steps? to reproduce|reproduc|repro\b|to reproduce)/i.test(text) || /^\s*\d+[.)]\s+/m.test(text),
    hasExpectedActual: /expected/i.test(text) && /(actual|instead|but got|received)/i.test(text),
    keywords,
  };
}

export function questionsForMissingInformation(signals: IssueSignals): string[] {
  const questions: string[] = [];
  if (!signals.hasReproSteps) {
    questions.push("What are the exact steps (or a minimal example) that trigger the problem?");
  }
  if (!signals.hasExpectedActual) {
    questions.push("What did you expect to happen, and what happened instead?");
  }
  if (signals.versions.length === 0) {
    questions.push("Which version of the project, runtime, and operating system are you using?");
  }
  if (signals.errorMessages.length === 0 && signals.stackFrames.length === 0) {
    questions.push("Can you share the full error message or stack trace?");
  }
  if (signals.codeBlocks.length === 0) {
    questions.push("Can you share the code, request, or command that produced the problem?");
  }
  return questions;
}

export function describeMissingInformation(signals: IssueSignals): string[] {
  const missing: string[] = [];
  if (!signals.hasReproSteps) {
    missing.push("No clear reproduction steps were found. Ask for the exact steps or a minimal example.");
  }
  if (!signals.hasExpectedActual) {
    missing.push("Expected versus actual behavior is not clearly stated.");
  }
  if (signals.versions.length === 0) {
    missing.push("No version information was found (project version, runtime, or OS).");
  }
  if (signals.errorMessages.length === 0 && signals.stackFrames.length === 0) {
    missing.push("No error message or stack trace was included.");
  }
  if (signals.codeBlocks.length === 0) {
    missing.push("No code or command snippet was included.");
  }
  return missing;
}
