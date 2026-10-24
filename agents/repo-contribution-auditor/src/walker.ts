/**
 * File system walker with hard limits.
 *
 * Respects: maxFiles, maxFileSizeBytes, maxTotalBytes, maxDepth.
 * Skips: symlinks, unreadable files, common non-source directories.
 * No shell is used anywhere in this module.
 *
 * Directories skipped (configurable via SKIP_DIRS):
 *   node_modules, .git, venv, .venv, env, dist, build, __pycache__,
 *   .pytest_cache, coverage, .nyc_output, .idea, .vscode
 */

import { readdirSync, statSync, readFileSync, lstatSync } from "node:fs";
import { join, relative } from "node:path";
import type { AuditLimits } from "./types.js";

export interface WalkedFile {
  /** Absolute path */
  absPath: string;
  /** Path relative to walk root */
  relPath: string;
  /** File content as string (UTF-8, best-effort) */
  content: string;
  /** Size in bytes */
  sizeBytes: number;
}

export interface WalkResult {
  files: WalkedFile[];
  truncated: boolean;
  truncationReason?: string;
  totalBytes: number;
  fileCount: number;
}

/** Directories that are never walked — they contain third-party or generated code */
const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "venv",
  ".venv",
  "env",
  "dist",
  "build",
  "__pycache__",
  ".pytest_cache",
  "coverage",
  ".nyc_output",
  ".idea",
  ".vscode",
]);

export function walkDir(rootDir: string, limits: AuditLimits): WalkResult {
  const result: WalkResult = {
    files: [],
    truncated: false,
    totalBytes: 0,
    fileCount: 0,
  };

  function recurse(dir: string, depth: number): void {
    if (result.truncated) return;
    if (depth > limits.maxDepth) {
      result.truncated = true;
      result.truncationReason = `Max depth ${limits.maxDepth} exceeded`;
      return;
    }

    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return; // unreadable directory
    }

    for (const entry of entries) {
      if (result.truncated) return;

      const absPath = join(dir, entry);

      // Use lstat to detect symlinks without following them
      let stat;
      try {
        stat = lstatSync(absPath);
      } catch {
        continue;
      }

      if (stat.isSymbolicLink()) {
        continue; // skip all symlinks
      }

      if (stat.isDirectory()) {
        // Skip known non-source directories
        if (SKIP_DIRS.has(entry)) continue;
        recurse(absPath, depth + 1);
        continue;
      }

      if (!stat.isFile()) continue;

      result.fileCount++;
      if (result.fileCount > limits.maxFiles) {
        result.truncated = true;
        result.truncationReason = `Max file count ${limits.maxFiles} exceeded`;
        return;
      }

      const sizeBytes = stat.size;
      if (sizeBytes > limits.maxFileSizeBytes) {
        // Include entry with truncated content marker
        result.files.push({
          absPath,
          relPath: relative(rootDir, absPath),
          content: "", // content skipped for oversized files
          sizeBytes,
        });
        continue;
      }

      result.totalBytes += sizeBytes;
      if (result.totalBytes > limits.maxTotalBytes) {
        result.truncated = true;
        result.truncationReason = `Max total size ${limits.maxTotalBytes} bytes exceeded`;
        return;
      }

      let content = "";
      try {
        content = readFileSync(absPath, "utf-8");
      } catch {
        content = ""; // unreadable content treated as empty
      }

      result.files.push({
        absPath,
        relPath: relative(rootDir, absPath),
        content,
        sizeBytes,
      });
    }
  }

  recurse(rootDir, 0);
  return result;
}
