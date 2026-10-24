/**
 * PR Sentinel - Git Tool
 * Extracts diffs, git status, changed files, and unified patches.
 */

import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/**
 * Execute git command safely
 * @param {string} cmd
 * @param {string} cwd
 * @returns {string}
 */
function runGit(cmd, cwd = process.cwd()) {
  try {
    return execSync(cmd, {
      cwd,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 10000,
    }).trim();
  } catch (err) {
    return '';
  }
}

/**
 * Get current git information
 * @param {string} cwd
 * @returns {Object}
 */
export function getGitInfo(cwd = process.cwd()) {
  const branch = runGit('git rev-parse --abbrev-ref HEAD', cwd) || 'unknown';
  const headCommit = runGit('git rev-parse --short HEAD', cwd) || 'unknown';
  const remoteUrl = runGit('git config --get remote.origin.url', cwd) || '';
  const isGitRepo = Boolean(runGit('git rev-parse --is-inside-work-tree', cwd));

  return {
    isGitRepo,
    branch,
    headCommit,
    remoteUrl,
  };
}

/**
 * Extract git diff from working tree, staged changes, or between references
 * @param {Object} options
 * @param {string} [options.cwd=process.cwd()]
 * @param {string} [options.base] e.g. 'main' or 'origin/main'
 * @param {string} [options.target] e.g. 'HEAD'
 * @param {boolean} [options.staged=false]
 * @returns {string} Unified diff string
 */
export function getGitDiff({ cwd = process.cwd(), base, target, staged = false } = {}) {
  if (base && target) {
    return runGit(`git diff ${base}...${target}`, cwd);
  }
  if (staged) {
    return runGit('git diff --cached', cwd);
  }

  // First try unstaged diff
  let diff = runGit('git diff', cwd);
  // If unstaged diff is empty, check staged
  if (!diff) {
    diff = runGit('git diff --cached', cwd);
  }
  // If still empty, check last commit diff
  if (!diff) {
    diff = runGit('git diff HEAD~1 HEAD', cwd);
  }

  return diff;
}

/**
 * Parse unified diff text into structured JSON object
 * @param {string} rawDiff
 * @returns {Array<Object>}
 */
export function parseUnifiedDiff(rawDiff) {
  if (!rawDiff || typeof rawDiff !== 'string') return [];

  const files = [];
  const fileBlocks = rawDiff.split(/^diff --git /m).filter(Boolean);

  for (const block of fileBlocks) {
    const lines = block.split('\n');
    const headerLine = lines[0] || '';
    const match = headerLine.match(/a\/(.*?)\s+b\/(.*)/);

    const oldPath = match ? match[1] : 'unknown';
    const newPath = match ? match[2] : 'unknown';

    let additions = 0;
    let deletions = 0;
    const hunks = [];
    let currentHunk = null;

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith('@@')) {
        if (currentHunk) hunks.push(currentHunk);
        currentHunk = { header: line, lines: [] };
      } else if (currentHunk) {
        currentHunk.lines.push(line);
        if (line.startsWith('+') && !line.startsWith('+++')) {
          additions++;
        } else if (line.startsWith('-') && !line.startsWith('---')) {
          deletions++;
        }
      }
    }

    if (currentHunk) hunks.push(currentHunk);

    files.push({
      oldPath,
      newPath,
      path: newPath !== '/dev/null' ? newPath : oldPath,
      additions,
      deletions,
      hunks,
      rawBlock: 'diff --git ' + block,
    });
  }

  return files;
}

/**
 * Scan directory recursively for project files when analyzing a folder directly
 * @param {string} dir
 * @param {Array<string>} [ignoreList]
 * @returns {Array<{ path: string, content: string }>}
 */
export function readDirectoryFiles(
  dir,
  ignoreList = [
    'node_modules',
    '.git',
    '.venv',
    'dist',
    'build',
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    '.env',
  ]
) {
  const results = [];

  function walk(currentDir) {
    let entries;
    try {
      entries = fs.readdirSync(currentDir, { withFileTypes: true });
    } catch (e) {
      return;
    }

    for (const entry of entries) {
      if (ignoreList.includes(entry.name)) continue;
      const fullPath = path.join(currentDir, entry.name);
      const relPath = path.relative(dir, fullPath).replace(/\\/g, '/');

      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile()) {
        // Read text files up to 256KB
        try {
          const stats = fs.statSync(fullPath);
          if (stats.size <= 256 * 1024) {
            const content = fs.readFileSync(fullPath, 'utf8');
            results.push({ path: relPath, content });
          }
        } catch (e) {
          // Ignore binary or unreadable files
        }
      }
    }
  }

  walk(dir);
  return results;
}

export default {
  getGitInfo,
  getGitDiff,
  parseUnifiedDiff,
  readDirectoryFiles,
};
