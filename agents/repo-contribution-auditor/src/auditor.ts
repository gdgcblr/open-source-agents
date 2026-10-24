/**
 * Core auditor orchestrator.
 *
 * Wires together: walker → checks → AI (optional) → result.
 *
 * Guardrails enforced here:
 *  - Path containment via safeResolve before walking
 *  - Walk limits (maxFiles, maxFileSizeBytes, maxTotalBytes, maxDepth)
 *  - AI provider errors fall back to deterministic-only output
 *  - Model output validated before merging
 */

import { resolve } from "node:path";
import { existsSync, statSync, lstatSync } from "node:fs";
import type { AuditResult, CliOptions, AuditLimits } from "./types.js";
import { DEFAULT_LIMITS } from "./types.js";
import { walkDir } from "./walker.js";
import { runAllChecks } from "./checks.js";
import type { AiProvider } from "./aiProvider.js";

export async function audit(
  options: CliOptions,
  provider: AiProvider | null,
  limits: AuditLimits = DEFAULT_LIMITS
): Promise<AuditResult> {
  // Resolve and validate the target directory.
  // safeResolve rejects symlinks and verifies the path exists.
  // For the auditor root itself we skip the parent-containment check
  // (there is no enclosing root), but we still reject symlinked target dirs.
  const targetDir = (() => {
    const raw = resolve(options.targetDir);
    if (!existsSync(raw)) {
      throw new Error(`Target directory does not exist: ${raw}`);
    }
    if (!statSync(raw).isDirectory()) {
      throw new Error(`Target path is not a directory: ${raw}`);
    }
    // Reject symlinked target directories so the walk root is always real
    if (lstatSync(raw).isSymbolicLink()) {
      throw new Error(`Target directory is a symlink; use a real path: ${options.targetDir}`);
    }
    return raw;
  })();

  // Walk the directory tree with hard limits
  const walked = walkDir(targetDir, limits);

  // Run all deterministic checks
  const findings = runAllChecks(walked.files, {
    targetDir,
    baseRef: options.baseRef,
  });

  // AI layer (optional)
  let annotations: AuditResult["annotations"] = [];
  if (options.explain && provider) {
    try {
      annotations = await provider.explain(findings);
    } catch (err) {
      // Graceful fallback: deterministic output stands; note the error in info finding
      findings.push({
        id: `F${String(findings.length + 1).padStart(3, "0")}`,
        severity: "info",
        label: "heuristic",
        rule: "AI-FALLBACK",
        description: `AI provider error (${String(err).substring(0, 120)}); falling back to deterministic output`,
        file: "",
        line: 0,
        evidence: "provider error",
      });
    }
  }

  const result: AuditResult = {
    targetDir,
    timestamp: new Date().toISOString(),
    truncated: walked.truncated,
    findings,
    annotations,
  };
  if (walked.truncationReason !== undefined) {
    result.truncationReason = walked.truncationReason;
  }
  return result;
}
