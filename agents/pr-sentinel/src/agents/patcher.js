/**
 * PR Sentinel - Patch Synthesizer Agent
 * Automatically generates unified diff patches to resolve security and compliance issues.
 */

import { generateFixPatches } from '../tools/patcher.js';
import { generateWithGemini } from '../models/gemini.js';
import { simulateAgentExecution } from '../models/mock.js';
import { config } from '../config.js';

export const PATCHER_AGENT_PROMPT = `You are PatchSynthesizer, an automated code correction agent.
Your mission is to take actionable security, quality, and compliance findings and generate unified diff patches to resolve them cleanly.

Respond with valid JSON containing:
{
  "agent": "PatchSynthesizer",
  "status": "READY" | "SKIPPED",
  "summary": "Summary of generated fixes",
  "patchCount": number,
  "patches": [
    {
      "targetFile": "path/to/file",
      "title": "Title of fix",
      "description": "What this patch fixes",
      "diff": "unified diff patch content..."
    }
  ]
}`;

export class PatcherAgent {
  constructor() {
    this.name = 'PatchSynthesizer';
  }

  async synthesize(context) {
    const rawIssues = [
      ...(context.securityResults?.findings || []),
      ...(context.qualityResults?.findings || []),
      ...(context.complianceResults?.findings || []),
    ];

    // Generate local deterministic patches for standard patterns
    const localPatches = generateFixPatches(rawIssues, {
      files: context.files || [],
      targetDir: context.targetDir || '.',
    });

    if (config.isLiveApiAvailable() && rawIssues.length > 0) {
      try {
        const actionableIssues = rawIssues.filter(
          i => i.severity === 'CRITICAL' || i.severity === 'HIGH' || i.type === 'credential_leak'
        );

        if (actionableIssues.length > 0) {
          const prompt = `Generate corrective unified diff patches for these critical issues:
${JSON.stringify(actionableIssues, null, 2)}`;

          const result = await generateWithGemini({
            systemInstruction: PATCHER_AGENT_PROMPT,
            prompt,
            jsonMode: true,
            temperature: 0.1,
          });

          if (result.data && result.data.patches?.length > 0) {
            return result.data;
          }
        }
      } catch (err) {
        // Fall back gracefully
      }
    }

    if (localPatches.length > 0) {
      return {
        agent: 'PatchSynthesizer',
        status: 'READY',
        summary: `Synthesized ${localPatches.length} corrective patch(es) addressing exposed secrets or missing templates.`,
        patchCount: localPatches.length,
        patches: localPatches,
      };
    }

    return simulateAgentExecution('patcher', {
      ...context,
      securityFindings: context.securityResults?.findings,
      qualityFindings: context.qualityResults?.findings,
      complianceFindings: context.complianceResults?.findings,
    });
  }
}

export default PatcherAgent;
