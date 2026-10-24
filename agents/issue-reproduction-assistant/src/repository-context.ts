import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { rankFiles } from "./localize.js";
import { extractSignals } from "./signals.js";

const MAX_FILES_TO_SCAN = 1_000;
const MAX_FILES_TO_INCLUDE = 40;
const MAX_FILE_BYTES = 16 * 1024;
const MAX_CONTEXT_CHARACTERS = 50_000;
const SUPPORTED_EXTENSIONS = new Set([
  ".c",
  ".cc",
  ".cpp",
  ".cs",
  ".css",
  ".go",
  ".h",
  ".hpp",
  ".html",
  ".java",
  ".js",
  ".jsx",
  ".json",
  ".md",
  ".mjs",
  ".py",
  ".rs",
  ".scss",
  ".sh",
  ".sql",
  ".toml",
  ".ts",
  ".tsx",
  ".xml",
  ".yaml",
  ".yml",
]);
const IGNORED_DIRECTORIES = new Set([
  "build",
  "coverage",
  "dist",
  "node_modules",
  "target",
  "vendor",
  "venv",
]);
const SENSITIVE_FILE_PATTERN =
  /(^\.env(?:\.|$)|secret|credential|password|token|\.pem$|\.key$|\.p12$|\.pfx$|lock$)/i;
const SECRET_ASSIGNMENT_PATTERN =
  /(["']?(?:api[_-]?key|access[_-]?token|secret|password|client[_-]?secret)["']?\s*[:=]\s*["']?)(?!your_|example|<)([^\s"'`,;]{8,})/gi;
const BEARER_PATTERN = /(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi;
const KNOWN_TOKEN_PATTERN =
  /\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{30,})\b/g;

export interface ContextFile {
  path: string;
  content: string;
}

export function redactSensitiveContent(content: string): string {
  return content
    .replace(
      /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
      "[REDACTED PRIVATE KEY]",
    )
    .replace(KNOWN_TOKEN_PATTERN, "[REDACTED TOKEN]")
    .replace(BEARER_PATTERN, "$1[REDACTED]")
    .replace(SECRET_ASSIGNMENT_PATTERN, "$1[REDACTED]");
}

function shouldSkipFile(fileName: string): boolean {
  return SENSITIVE_FILE_PATTERN.test(fileName) ||
    !SUPPORTED_EXTENSIONS.has(path.extname(fileName).toLowerCase());
}

export async function readRepositoryFiles(repositoryPath: string): Promise<ContextFile[]> {
  const root = path.resolve(repositoryPath);
  const rootInfo = await stat(root);
  if (!rootInfo.isDirectory()) {
    throw new Error(`Repository path is not a directory: ${root}`);
  }

  const files: ContextFile[] = [];
  const pendingDirectories = [root];
  let scannedFiles = 0;

  while (pendingDirectories.length > 0 && scannedFiles < MAX_FILES_TO_SCAN) {
    const directory = pendingDirectories.pop();
    if (!directory) {
      break;
    }

    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));

    for (const entry of entries) {
      if (entry.name.startsWith(".") || entry.isSymbolicLink()) {
        continue;
      }

      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!IGNORED_DIRECTORIES.has(entry.name.toLowerCase())) {
          pendingDirectories.push(absolutePath);
        }
        continue;
      }

      if (!entry.isFile() || shouldSkipFile(entry.name)) {
        continue;
      }

      scannedFiles += 1;
      if (scannedFiles > MAX_FILES_TO_SCAN) {
        break;
      }

      const fileInfo = await stat(absolutePath);
      if (fileInfo.size > MAX_FILE_BYTES) {
        continue;
      }

      const originalContent = await readFile(absolutePath, "utf8");
      if (originalContent.includes("\u0000")) {
        continue;
      }

      files.push({
        path: path.relative(root, absolutePath),
        content: redactSensitiveContent(originalContent),
      });
    }
  }

  return files;
}

export async function collectRepositoryContext(
  repositoryPath: string,
  issueText: string,
): Promise<ContextFile[]> {
  const files = await readRepositoryFiles(repositoryPath);
  const ranked = rankFiles(files, extractSignals(issueText));
  const selected: ContextFile[] = [];
  let characterCount = 0;

  for (const candidate of ranked) {
    const remaining = MAX_CONTEXT_CHARACTERS - characterCount;
    if (selected.length >= MAX_FILES_TO_INCLUDE || remaining <= 0) {
      break;
    }
    const content = candidate.content.slice(0, remaining);
    selected.push({ path: candidate.path, content });
    characterCount += content.length;
  }

  return selected;
}
