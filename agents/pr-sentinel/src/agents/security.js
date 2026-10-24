/**
 * PR Sentinel - Security Sentinel Agent
 * Specializes in identifying leaked credentials, private keys, command injection, and security flaws.
 */

import { scanContentForSecrets } from '../tools/secrets.js';
import { analyzeCodeQuality } from '../tools/ast.js';
import { generateWithGemini } from '../models/gemini.js';
import { simulateAgentExecution } from '../models/mock.js';
import { config } from '../config.js';

export const SECURITY_AGENT_PROMPT = `You are SecuritySentinel, an elite Application Security Engineer auditing Pull Requests in open-source AI agent repositories.
Your mission is to rigorously detect:
1. Hardcoded API keys, tokens, private keys, or passwords.
2. Unsafe shell execution (exec, eval, system commands).
3. Arbitrary code execution or uncontained execution loops.
4. Insecure logging of sensitive authorization tokens.

Respond with valid JSON containing:
{
  "agent": "SecuritySentinel",
  "status": "PASS" | "WARN" | "FAIL",
  "score": number (0-100),
  "summary": "Clear, concise paragraph summarizing security posture",
  "findings": [
    {
      "id": "SEC-...",
      "type": "credential_leak" | "unsafe_execution" | "injection_risk" | "info",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "title": "Short title",
      "description": "Detailed explanation of risk",
      "file": "path/to/file",
      "line": line_number,
      "recommendation": "Concrete fix instruction"
    }
  ]
}`;

export class SecurityAgent {
  constructor() {
    this.name = 'SecuritySentinel';
  }

  async audit(context) {
    const rawSecrets = [];
    const astIssues = [];

    // Run local deterministic scanners on changed files or diff
    if (context.files) {
      for (const file of context.files) {
        const found = scanContentForSecrets(file.content, file.path);
        rawSecrets.push(...found);

        const astFound = analyzeCodeQuality(file.content, file.path);
        astIssues.push(...astFound);
      }
    }

    if (context.rawDiff) {
      const diffSecrets = scanContentForSecrets(context.rawDiff, 'diff');
      for (const s of diffSecrets) {
        if (!rawSecrets.some(r => r.maskedSecret === s.maskedSecret)) {
          rawSecrets.push(s);
        }
      }
    }

    // If Gemini is available and not in mock mode, perform reasoning
    if (config.isLiveApiAvailable()) {
      try {
        const prompt = `Perform security audit on these PR changes:
Repository Files / Diffs:
${JSON.stringify({
  filesChanged: context.files?.map(f => f.path) || [],
  detectedRawSecrets: rawSecrets,
  staticAnalysisIssues: astIssues,
  sampleDiff: context.rawDiff?.slice(0, 4000) || '',
}, null, 2)}
Ensure all detected secrets are flagged with severity CRITICAL.`;

        const result = await generateWithGemini({
          systemInstruction: SECURITY_AGENT_PROMPT,
          prompt,
          jsonMode: true,
          temperature: 0.1,
        });

        if (result.data) {
          return {
            ...result.data,
            rawSecrets,
          };
        }
      } catch (err) {
        // Fall back gracefully to simulation
      }
    }

    // Fallback simulation mode
    return simulateAgentExecution('security', {
      ...context,
      rawSecrets,
      astIssues,
    });
  }
}

export default SecurityAgent;
