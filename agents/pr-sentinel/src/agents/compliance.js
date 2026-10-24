/**
 * PR Sentinel - Compliance Auditor Agent
 * Verifies repository standards, documentation completeness, and contribution isolation.
 */

import { auditProjectCompliance } from '../tools/compliance.js';
import { generateWithGemini } from '../models/gemini.js';
import { simulateAgentExecution } from '../models/mock.js';
import { config } from '../config.js';

export const COMPLIANCE_AGENT_PROMPT = `You are ComplianceAuditor, a Lead Open-Source Maintainer enforcing repository contribution guidelines.
Your mission is to verify:
1. All contribution files reside in a dedicated agents/<slug> or tools/<slug> directory with lowercase kebab-case naming.
2. README.md is fully completed from template/README.md without placeholder tokens like [Project Name].
3. .env.example exists with placeholder values.
4. Dependency manifest (package.json, requirements.txt) is present.
5. Isolation: No modifications to other projects' folders or root build files.

Respond with valid JSON containing:
{
  "agent": "ComplianceAuditor",
  "status": "PASS" | "WARN" | "FAIL",
  "score": number (0-100),
  "summary": "Concise compliance report",
  "findings": [
    {
      "id": "COMP-...",
      "severity": "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "title": "Short title",
      "description": "Rule violation detail",
      "recommendation": "Step to resolve violation"
    }
  ]
}`;

export class ComplianceAgent {
  constructor() {
    this.name = 'ComplianceAuditor';
  }

  async audit(context) {
    const projectDir = context.targetDir || '.';
    const changedFiles = context.diffSummary?.files?.map(f => f.path) || [];
    const complianceResults = auditProjectCompliance(projectDir, changedFiles);

    if (config.isLiveApiAvailable()) {
      try {
        const prompt = `Evaluate compliance for this submission:
Compliance audit results:
${JSON.stringify(complianceResults, null, 2)}`;

        const result = await generateWithGemini({
          systemInstruction: COMPLIANCE_AGENT_PROMPT,
          prompt,
          jsonMode: true,
          temperature: 0.1,
        });

        if (result.data) {
          return {
            ...result.data,
            complianceDetails: complianceResults,
          };
        }
      } catch (e) {
        // Fall back gracefully
      }
    }

    return simulateAgentExecution('compliance', {
      ...context,
      complianceAudit: complianceResults,
    });
  }
}

export default ComplianceAgent;
