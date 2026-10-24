/**
 * Path containment utilities.
 *
 * Uses `fs.realpathSync` to resolve symlinks and normalise paths.
 * Any path that does not resolve INSIDE rootDir is rejected.
 * Symlinks that escape the root are rejected.
 *
 * Cross-platform: works on Windows (backslash paths) and POSIX (forward slash).
 * NOTE: No shell is invoked here. All operations are pure fs calls.
 */

import { realpathSync, existsSync, lstatSync } from "node:fs";
import { resolve, relative } from "node:path";

/**
 * Return true if `rel` (the result of path.relative(root, target)) is safely
 * inside root: it must not start with ".." and must not be an absolute path.
 * Works on Windows (backslash) and POSIX (forward slash).
 */
function isInsideRoot(rel: string): boolean {
  // Empty string = same directory as root = contained
  if (rel === "") return true;
  // Must not escape via ".." in any position
  return !rel.startsWith("..") && rel !== "..";
}

/**
 * Resolve `rawPath` and verify it is strictly inside `rootDir`.
 *
 * @returns The resolved absolute path.
 * @throws {RangeError} if the path is outside rootDir or is a symlink.
 */
export function safeResolve(rootDir: string, rawPath: string): string {
  const realRoot = realpathSync(rootDir);

  // First resolve without following symlinks to detect them early
  const joined = resolve(rootDir, rawPath);

  if (!existsSync(joined)) {
    throw new RangeError(`Path does not exist: ${rawPath}`);
  }

  const stat = lstatSync(joined);
  if (stat.isSymbolicLink()) {
    throw new RangeError(`Symlinks are not allowed: ${rawPath}`);
  }

  // Now resolve following any remaining symlinks in parent chain
  const realJoined = realpathSync(joined);

  // Strict containment
  const rel = relative(realRoot, realJoined);
  if (!isInsideRoot(rel)) {
    throw new RangeError(
      `Path traversal detected: ${rawPath} resolves outside root`
    );
  }

  return realJoined;
}

/**
 * Return true if `absPath` is strictly contained within `rootDir`
 * (after realpath resolution).  Does NOT throw; returns false on any error.
 */
export function isContained(rootDir: string, absPath: string): boolean {
  try {
    const realRoot = realpathSync(rootDir);
    const realPath = realpathSync(absPath);
    const rel = relative(realRoot, realPath);
    return isInsideRoot(rel);
  } catch {
    return false;
  }
}

/**
 * Sanitise a relative path for safe display.
 * Strips leading slashes/dots that could confuse display.
 */
export function sanitizeRelPath(rel: string): string {
  return rel.replace(/^[./\\]+/, "") || ".";
}
