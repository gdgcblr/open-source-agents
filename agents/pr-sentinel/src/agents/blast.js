/**
 * PR Sentinel - Blast Radius & Semantic Regression Forecaster Agent
 * Simulates downstream production breakages, ripple impact, and architectural regression risks.
 */

import { extractExportedSymbols, findDownstreamCallers, calculateBlastRadius } from '../tools/blast.js';
import { generateWithGemini } from '../models/gemini.js';
import { config } from '../config.js';

export const BLAST_AGENT_PROMPT = `You are BlastRadiusPredictor, an elite Principal Site Reliability and Architecture Forecaster.
Your job is to analyze the symbols modified in a Pull Request, inspect the downstream calling files that rely on those symbols, and forecast EXACTLY what will break in production if merged.

Respond with valid JSON:
{
  "agent": "BlastRadiusPredictor",
  "status": "PASS" | "WARN" | "CRITICAL",
  "blastScore": number (0 to 100),
  "containmentVerdict": "ISOLATED" | "MODERATE_DOWNSTREAM_RIPPLE" | "CATASTROPHIC_POTENTIAL",
  "summary": "Executive explanation of the downstream blast radius",
  "downstreamImpacts": [
    {
      "impactedFile": "path/to/caller.js",
      "brokenSymbol": "functionName",
      "predictedFailure": "e.g., TypeError: Cannot read property 'id' of undefined",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM",
      "preventionFix": "What caller or PR author must update"
    }
  ],
  "contractIntegrity": "STABLE" | "BREAKING_CHANGE_DETECTED"
}`;

export class BlastAgent {
  constructor() {
    this.name = 'BlastRadiusPredictor';
  }

  /**
   * Forecast blast radius and downstream breakages
   * @param {Object} context
   * @returns {Promise<Object>} Blast radius forecast
   */
  async forecast(context) {
    const changedFiles = context.files || [];
    const allFiles = context.allProjectFiles || changedFiles;

    // 1. Extract all exported symbols modified in this PR
    const modifiedSymbols = new Set();
    let hasTestUpdates = false;

    for (const file of changedFiles) {
      if (/test|spec/i.test(file.path)) {
        hasTestUpdates = true;
      }
      const symbols = extractExportedSymbols(file.content || '');
      for (const s of symbols) modifiedSymbols.add(s);
    }

    const symbolList = Array.from(modifiedSymbols);
    const changedPaths = changedFiles.map(f => f.path);

    // 2. Discover untouched downstream callers across the codebase
    const downstreamCallers = findDownstreamCallers(symbolList, allFiles, changedPaths);

    // 3. Compute deterministic Blast Radius Metrics
    const blastMetrics = calculateBlastRadius({
      totalFiles: allFiles.length || 1,
      impactedFilesCount: downstreamCallers.length,
      modifiedSymbolsCount: symbolList.length,
      hasTestCoverageUpdates: hasTestUpdates,
    });

    // 4. If Gemini is available, simulate semantic runtime failure modes
    if (config.isLiveApiAvailable() && downstreamCallers.length > 0) {
      try {
        const prompt = `Analyze these modified exported symbols and their downstream callers to forecast runtime regressions:
Modified Exported Symbols: ${JSON.stringify(symbolList)}
Downstream Untouched Callers: ${JSON.stringify(downstreamCallers.slice(0, 8), null, 2)}
PR Changed Code Snippets: ${JSON.stringify(changedFiles.slice(0, 3).map(f => ({ path: f.path, snippet: (f.content || '').slice(0, 800) })), null, 2)}`;

        const result = await generateWithGemini({
          systemInstruction: BLAST_AGENT_PROMPT,
          prompt,
          jsonMode: true,
          temperature: 0.2,
        });

        if (result.data && typeof result.data.blastScore === 'number') {
          return {
            ...result.data,
            metrics: blastMetrics,
            downstreamCallers,
          };
        }
      } catch (err) {
        // Fall back gracefully
      }
    }

    // High-fidelity local simulation output
    const isCatastrophic = blastMetrics.score > 60;
    const isModerate = blastMetrics.score > 30;

    return {
      agent: 'BlastRadiusPredictor',
      status: isCatastrophic ? 'CRITICAL' : isModerate ? 'WARN' : 'PASS',
      blastScore: blastMetrics.score,
      containmentVerdict: blastMetrics.containmentCategory,
      summary: downstreamCallers.length > 0
        ? `PR modifies ${symbolList.length} exported symbol(s) with ${downstreamCallers.length} downstream caller(s) across the project. Downstream regression risk is ${blastMetrics.containmentCategory.toLowerCase().replace(/_/g, ' ')}.`
        : `Changes are hermetically contained. No external downstream callers detected in repository.`,
      contractIntegrity: downstreamCallers.length > 2 && !hasTestUpdates ? 'BREAKING_CHANGE_DETECTED' : 'STABLE',
      metrics: blastMetrics,
      downstreamImpacts: downstreamCallers.map(caller => ({
        impactedFile: caller.file,
        brokenSymbol: caller.references.join(', '),
        predictedFailure: caller.isTestFile
          ? 'Unit test suite contract verification requires alignment with modified signature'
          : `Downstream consumer calls [${caller.references.join(', ')}] which underwent interface modification in this PR`,
        severity: caller.isTestFile ? 'MEDIUM' : 'HIGH',
        preventionFix: `Verify contract compatibility and run integration test coverage for ${caller.file}`,
      })),
      downstreamCallers,
    };
  }
}

export default BlastAgent;
