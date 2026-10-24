/**
 * PR Sentinel - Blast Radius & Impact Analyzer Tool
 * Analyzes AST imports, exports, and caller references to calculate downstream impact.
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * Extract exported symbols (functions, classes, constants) from source code
 * @param {string} content
 * @returns {Array<string>} Exported identifier names
 */
export function extractExportedSymbols(content = '') {
  const exports = new Set();
  
  // export const/let/var/function/class name
  const namedRegex = /export\s+(?:async\s+)?(?:const|let|var|function|class)\s+([a-zA-Z0-9_$]+)/g;
  let match;
  while ((match = namedRegex.exec(content)) !== null) {
    if (match[1]) exports.add(match[1]);
  }

  // export { a, b as c }
  const blockRegex = /export\s*\{([^}]+)\}/g;
  while ((match = blockRegex.exec(content)) !== null) {
    const symbols = match[1].split(',').map(s => s.trim().split(/\s+as\s+/).pop());
    for (const s of symbols) {
      if (s && /^[a-zA-Z0-9_$]+$/.test(s)) exports.add(s);
    }
  }

  // CommonJS: module.exports = { a, b } or exports.foo = ...
  const cjsRegex = /(?:module\.)?exports\.([a-zA-Z0-9_$]+)\s*=/g;
  while ((match = cjsRegex.exec(content)) !== null) {
    if (match[1]) exports.add(match[1]);
  }

  return Array.from(exports);
}

/**
 * Scan all files in directory to find references to modified symbols
 * @param {Array<string>} modifiedSymbols Symbols modified in PR
 * @param {Array<{ path: string, content: string }>} allFiles All codebase files
 * @param {Array<string>} changedFilePaths Files changed in the PR
 * @returns {Array<{ file: string, references: Array<string>, riskLevel: string }>}
 */
export function findDownstreamCallers(modifiedSymbols = [], allFiles = [], changedFilePaths = []) {
  if (modifiedSymbols.length === 0 || allFiles.length === 0) return [];

  const callers = [];
  const normalizedChanged = changedFilePaths.map(p => p.replace(/\\/g, '/'));

  for (const file of allFiles) {
    const normPath = file.path.replace(/\\/g, '/');
    // Skip files that were themselves modified in the PR (we want downstream untouched files)
    if (normalizedChanged.some(c => normPath.endsWith(c) || c.endsWith(normPath))) continue;

    const matchedSymbols = [];
    for (const sym of modifiedSymbols) {
      // Look for symbol usage (word boundary)
      const regex = new RegExp(`\\b${sym}\\b`, 'g');
      if (regex.test(file.content || '')) {
        matchedSymbols.push(sym);
      }
    }

    if (matchedSymbols.length > 0) {
      const isTestFile = /test|spec|\.test\.|\.spec\./i.test(normPath);
      callers.push({
        file: normPath,
        references: matchedSymbols,
        isTestFile,
        riskLevel: isTestFile ? 'VERIFICATION_DEBT' : 'PRODUCTION_REGRESSION_RISK',
      });
    }
  }

  return callers;
}

/**
 * Compute composite Blast Radius Score (0% = perfectly contained, 100% = critical system-wide risk)
 * @param {Object} params
 * @param {number} params.totalFiles
 * @param {number} params.impactedFilesCount
 * @param {number} params.modifiedSymbolsCount
 * @param {boolean} params.hasTestCoverageUpdates
 * @returns {Object} Blast radius metrics
 */
export function calculateBlastRadius({
  totalFiles = 1,
  impactedFilesCount = 0,
  modifiedSymbolsCount = 0,
  hasTestCoverageUpdates = false,
}) {
  const fileRatio = totalFiles > 0 ? (impactedFilesCount / totalFiles) * 100 : 0;
  let rawScore = Math.min(100, Math.round(fileRatio * 2 + modifiedSymbolsCount * 8));

  // If critical shared symbols are modified but no test files were touched, penalize
  if (impactedFilesCount > 0 && !hasTestCoverageUpdates) {
    rawScore = Math.min(100, rawScore + 15);
  }

  let containmentCategory = 'ISOLATED';
  let badgeColor = '#22c55e'; // Green

  if (rawScore > 60) {
    containmentCategory = 'CATASTROPHIC_POTENTIAL';
    badgeColor = '#ef4444'; // Red
  } else if (rawScore > 30) {
    containmentCategory = 'MODERATE_DOWNSTREAM_RIPPLE';
    badgeColor = '#f59e0b'; // Amber
  } else if (rawScore > 10) {
    containmentCategory = 'LOW_SURFACE_RIPPLE';
    badgeColor = '#3b82f6'; // Blue
  }

  return {
    score: rawScore,
    containmentCategory,
    badgeColor,
    impactedFilesCount,
    modifiedSymbolsCount,
    untestedDownstreamCallers: impactedFilesCount > 0 && !hasTestCoverageUpdates,
  };
}

export default {
  extractExportedSymbols,
  findDownstreamCallers,
  calculateBlastRadius,
};
