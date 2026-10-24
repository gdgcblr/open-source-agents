/**
 * All deterministic check rules.
 *
 * Each rule receives the walked file set and emits zero or more Findings.
 * Rules never exec shell commands and never read outside the walked file set.
 *
 * Rule IDs:
 *  R01 — README sections / no leftover placeholders
 *  R02 — Manifest + lockfile present
 *  R03 — .env.example present; no .env tracked; env vars documented
 *  R04 — Secret scan (redacted evidence)
 *  R05 — .gitignore covers .env and node_modules / venv
 *  R06 — Folder name is kebab-case and not generic
 *  R07 — Scope check (git diff --name-only via execFile)
 */

import { execFileSync } from "node:child_process";
import { basename, join } from "node:path";
import type { Finding, Severity } from "./types.js";
import type { WalkedFile } from "./walker.js";
import { scanSecrets } from "./secretScanner.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _findingSeq = 0;
function nextId(): string {
  return `F${String(++_findingSeq).padStart(3, "0")}`;
}

function finding(
  severity: Severity,
  rule: string,
  description: string,
  file: string,
  line: number,
  evidence: string,
  label: "verified" | "heuristic" = "heuristic"
): Finding {
  return {
    id: nextId(),
    severity,
    label,
    rule,
    description,
    file,
    line,
    evidence,
  };
}

/** Normalise a path to use forward slashes regardless of OS. */
function normSep(p: string): string {
  return p.replace(/\\/g, "/");
}

function fileByName(files: WalkedFile[], name: string): WalkedFile | undefined {
  const normName = normSep(name);
  const matches = files.filter((f) => {
    const r = normSep(f.relPath);
    return r === normName || r.endsWith(`/${normName}`);
  });
  if (matches.length === 0) return undefined;
  // Prefer the shallowest match (root-level file has shortest path)
  return matches.reduce((a, b) => (a.relPath.length <= b.relPath.length ? a : b));
}

function filesByExtension(files: WalkedFile[], ext: string): WalkedFile[] {
  return files.filter((f) => f.relPath.endsWith(ext));
}

// ---------------------------------------------------------------------------
// R01 — README sections
// ---------------------------------------------------------------------------

const REQUIRED_SECTIONS = [
  "## Overview",
  "## Technical Stack",
  "## Architecture",
  "## Prerequisites",
  "## Installation",
  "## Configuration",
  "## How to Run",
  "## Example",
  "## How to Test",
  "## Known Limitations",
  "## Security",
  "## License",
];

// Template placeholder patterns that must NOT appear in a completed README
const PLACEHOLDER_PATTERNS = [
  /\[Project Name\]/,
  /\[One-sentence summary/,
  /Feature 1:/,
  /Feature 2:/,
  /\[Language Runtime/,
  /\[Package manager/,
  /\[Required API keys/,
  /python main\.py$/m,
  /\[User Input\] -->/,
  /Analyze the repository structure of gdgcblr/,
  /Analysis completed:/,
  /Add caching for external API responses/,
];

export function checkReadme(files: WalkedFile[]): Finding[] {
  const findings: Finding[] = [];
  const readme = fileByName(files, "README.md");

  if (!readme) {
    findings.push(
      finding("high", "R01", "README.md not found", "README.md", 0, "file missing", "verified")
    );
    return findings;
  }

  const content = readme.content;
  const lines = content.split("\n");

  // Check required sections against the FULL content (headings don't appear in code blocks normally)
  for (const section of REQUIRED_SECTIONS) {
    const pattern = new RegExp(section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    if (!pattern.test(content)) {
      findings.push(
        finding(
          "medium",
          "R01",
          `README.md is missing section: ${section}`,
          readme.relPath,
          0,
          `Section "${section}" not found`,
          "verified"
        )
      );
    }
  }

  // Strip fenced code blocks before scanning for leftover placeholders.
  // Code blocks in example output sections must not trigger placeholder detection.
  // A genuine unfilled placeholder in normal prose text will still be caught.
  const contentWithoutCodeBlocks = content.replace(/```[\s\S]*?```/g, (match) =>
    // Replace each line in the block with an empty line to preserve line numbers
    match
      .split("\n")
      .map(() => "")
      .join("\n")
  );
  const linesWithoutCodeBlocks = contentWithoutCodeBlocks.split("\n");

  // Check for leftover placeholders (outside code blocks only)
  for (const pattern of PLACEHOLDER_PATTERNS) {
    const match = contentWithoutCodeBlocks.match(pattern);
    if (match) {
      const idx = linesWithoutCodeBlocks.findIndex((l) => pattern.test(l));
      findings.push(
        finding(
          "medium",
          "R01",
          "README.md contains leftover template placeholder",
          readme.relPath,
          idx + 1,
          `Placeholder: "${match[0]?.substring(0, 60)}"`,
          "heuristic"
        )
      );
    }
  }

  return findings;
}


// ---------------------------------------------------------------------------
// R02 — Manifest + lockfile
// ---------------------------------------------------------------------------

const MANIFEST_NAMES = [
  "package.json",
  "requirements.txt",
  "pyproject.toml",
  "setup.py",
  "Cargo.toml",
  "go.mod",
];
const LOCKFILE_NAMES = [
  "package-lock.json",
  "yarn.lock",
  "pnpm-lock.yaml",
  "uv.lock",
  "poetry.lock",
  "Cargo.lock",
  "go.sum",
];

export function checkManifest(files: WalkedFile[]): Finding[] {
  const findings: Finding[] = [];

  const hasManifest = MANIFEST_NAMES.some((n) => fileByName(files, n));
  if (!hasManifest) {
    findings.push(
      finding("high", "R02", "No dependency manifest found (package.json, requirements.txt, etc.)", "", 0, "manifest missing", "verified")
    );
    return findings; // no point checking lockfile
  }

  const hasPkgJson = !!fileByName(files, "package.json");
  if (hasPkgJson) {
    const hasLock = LOCKFILE_NAMES.some((n) => fileByName(files, n));
    if (!hasLock) {
      findings.push(
        finding("medium", "R02", "package.json present but no lockfile found (package-lock.json / yarn.lock / pnpm-lock.yaml)", "package.json", 0, "lockfile missing", "verified")
      );
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// R03 — .env.example + no tracked .env + env vars documented
// ---------------------------------------------------------------------------

export function checkEnvExample(files: WalkedFile[]): Finding[] {
  const findings: Finding[] = [];

  const envExample = fileByName(files, ".env.example");
  if (!envExample) {
    findings.push(
      finding("high", "R03", ".env.example is missing", ".env.example", 0, "file missing", "verified")
    );
    return findings;
  }

  // Check no .env (non-example) is present in the walked set
  const trackedEnv = files.find((f) => {
    const r = normSep(f.relPath);
    return (
      (r === ".env" || r.endsWith("/.env")) &&
      !r.endsWith(".example") &&
      !r.endsWith(".sample")
    );
  });
  if (trackedEnv) {
    findings.push(
      finding("high", "R03", ".env file is present and may contain real secrets", trackedEnv.relPath, 0, ".env file found in project", "verified")
    );
  }

  // Cross-check: env vars declared in .env.example vs README table
  const readme = fileByName(files, "README.md");
  if (readme) {
    const exampleVars = [...envExample.content.matchAll(/^([A-Z][A-Z0-9_]{2,})\s*=/gm)].map((m) => m[1]);
    for (const v of exampleVars) {
      if (v && !readme.content.includes(v)) {
        findings.push(
          finding(
            "low",
            "R03",
            `Env var ${v} in .env.example is not documented in README.md`,
            ".env.example",
            0,
            `Variable: ${v}`,
            "heuristic"
          )
        );
      }
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// R04 — Secret scan
// ---------------------------------------------------------------------------

// Files to skip from secret scanning (non-source metadata; lockfiles, etc.)
// NOTE: test files are NOT skipped — test fixtures must use runtime concatenation
// rather than literal secret strings so scanning works correctly on all source files.
const SKIP_SECRET_SCAN = new Set([
  ".gitignore",
  "package-lock.json",
  "yarn.lock",
  "pnpm-lock.yaml",
]);

export function checkSecrets(files: WalkedFile[]): Finding[] {
  const findings: Finding[] = [];

  for (const f of files) {
    const name = basename(f.relPath);
    if (SKIP_SECRET_SCAN.has(name)) continue;
    if (!f.content) continue; // oversized/unreadable

    const matches = scanSecrets(f.content);
    for (const m of matches) {
      findings.push(
        finding(
          "high",
          "R04",
          `Possible secret detected (${m.pattern})`,
          f.relPath,
          m.line,
          m.redactedEvidence,
          "heuristic"
        )
      );
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// R05 — .gitignore coverage
// ---------------------------------------------------------------------------

const REQUIRED_GITIGNORE_PATTERNS = [
  { pattern: /^\.env$|^\.env(?:\.\*)?/, label: ".env" },
  { pattern: /node_modules\//, label: "node_modules/" },
  { pattern: /\bvenv\/|\b\.venv\/|\benv\//, label: "venv/ or .venv/" },
];

export function checkGitignore(files: WalkedFile[]): Finding[] {
  const findings: Finding[] = [];
  const gi = fileByName(files, ".gitignore");

  if (!gi) {
    findings.push(
      finding("high", "R05", ".gitignore is missing", ".gitignore", 0, "file missing", "verified")
    );
    return findings;
  }

  const lines = gi.content.split("\n");
  for (const { pattern, label } of REQUIRED_GITIGNORE_PATTERNS) {
    const hasIt = lines.some((l) => pattern.test(l.trim()));
    if (!hasIt) {
      findings.push(
        finding(
          "medium",
          "R05",
          `.gitignore does not cover: ${label}`,
          gi.relPath,
          0,
          `Missing pattern for: ${label}`,
          "verified"
        )
      );
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// R06 — Folder name
// ---------------------------------------------------------------------------

const GENERIC_NAMES = new Set([
  "agent", "my-agent", "final-project", "test", "demo", "project",
  "example", "sample", "temp", "tmp", "new-agent", "ai-agent",
]);

export function checkFolderName(targetDir: string): Finding[] {
  const findings: Finding[] = [];
  const name = basename(targetDir);

  // Must be lowercase kebab-case: only a-z, 0-9, hyphen
  if (!/^[a-z][a-z0-9-]+$/.test(name)) {
    findings.push(
      finding(
        "medium",
        "R06",
        `Folder name "${name}" is not valid lowercase kebab-case`,
        "",
        0,
        `Folder: ${name}`,
        "verified"
      )
    );
  }

  if (GENERIC_NAMES.has(name)) {
    findings.push(
      finding(
        "medium",
        "R06",
        `Folder name "${name}" is too generic; choose a descriptive name`,
        "",
        0,
        `Folder: ${name}`,
        "verified"
      )
    );
  }

  return findings;
}

// ---------------------------------------------------------------------------
// R07 — Scope check
// ---------------------------------------------------------------------------

/**
 * Run `git diff --name-only <baseRef>` via execFile (no shell).
 * Flag any changed file outside the project slug path (allowing one
 * index-row edit in agents/README.md or tools/README.md).
 *
 * Returns empty array if git is not available or not in a repo.
 */
export function checkScope(targetDir: string, baseRef: string): Finding[] {
  const findings: Finding[] = [];

  let output: string;
  try {
    const buf = execFileSync(
      "git",
      ["diff", "--name-only", baseRef],
      {
        cwd: targetDir,
        shell: false,
        timeout: 10_000,
        maxBuffer: 1024 * 1024,
        // Suppress subprocess stderr so git error messages don't bleed into CLI output
        stdio: ["ignore", "pipe", "ignore"],
      }
    );
    output = buf.toString("utf-8");
  } catch {
    // Not a git repo, or git unavailable — skip this check
    return [
      finding(
        "info",
        "R07",
        `Scope check skipped: could not run git diff against "${baseRef}"`,
        "",
        0,
        "git not available or base ref not found",
        "heuristic"
      ),
    ];
  }

  const slug = basename(targetDir);
  const allowedPrefixes = [
    `agents/${slug}/`,
    `tools/${slug}/`,
    "agents/README.md",
    "tools/README.md",
  ];

  const changedFiles = output.split("\n").filter(Boolean);

  for (const f of changedFiles) {
    const allowed = allowedPrefixes.some((p) => f.startsWith(p) || f === p);
    if (!allowed) {
      findings.push(
        finding(
          "high",
          "R07",
          `Changed file outside allowed scope: ${f}`,
          f,
          0,
          `File "${f}" is outside agents/${slug}/ (and not a single index-row edit)`,
          "verified"
        )
      );
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// Aggregate runner
// ---------------------------------------------------------------------------

export interface CheckOptions {
  targetDir: string;
  baseRef: string;
}

export function runAllChecks(
  files: WalkedFile[],
  options: CheckOptions
): Finding[] {
  // Reset sequence for each run (idempotent in tests)
  _findingSeq = 0;

  return [
    ...checkReadme(files),
    ...checkManifest(files),
    ...checkEnvExample(files),
    ...checkSecrets(files),
    ...checkGitignore(files),
    ...checkFolderName(options.targetDir),
    ...checkScope(options.targetDir, options.baseRef),
  ];
}
