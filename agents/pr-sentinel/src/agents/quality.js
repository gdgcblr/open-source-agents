/**
 * PR Sentinel - Quality Critic Agent
 * Reviews code architecture, error resilience, modular design, and maintainability.
 */

import { generateWithGemini } from '../models/gemini.js';
import { simulateAgentExecution } from '../models/mock.js';
import { config } from '../config.js';

export const QUALITY_AGENT_PROMPT = `You are QualityCritic, a Principal Software Architect conducting code reviews for open-source AI agent repositories.
Your mission is to evaluate:
1. Error resilience (handling network failures, API rate limits, invalid JSON, unexpected tool outputs).
2. Code modularity and separation of concerns (tools vs agents vs models vs UI).
3. Asynchronous programming correctness (handling promise rejections, timeouts, memory leaks).
4. Code clarity, documentation, and maintainability.

Respond with valid JSON containing:
{
  "agent": "QualityCritic",
  "status": "PASS" | "WARN" | "FAIL",
  "score": number (0-100),
  "summary": "Concise architectural and code quality assessment",
  "findings": [
    {
      "id": "QA-...",
      "type": "resilience" | "architecture" | "async_flow" | "performance",
      "severity": "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "title": "Short title",
      "description": "Explanation of design or quality issue",
      "file": "path/to/file",
      "line": line_number,
      "recommendation": "Refactoring suggestion"
    }
  ]
}`;

export class QualityAgent {
  constructor() {
    this.name = 'QualityCritic';
  }

  async audit(context) {
    if (config.isLiveApiAvailable()) {
      try {
        const fileSnippets = (context.files || [])
          .filter(f => /\.(?:js|mjs|cjs|ts|py|go|rs)$/i.test(f.path))
          .slice(0, 5)
          .map(f => ({
            path: f.path,
            preview: f.content.slice(0, 1500),
          }));

        const prompt = `Review the code quality and architecture of these files in this pull request:
Files:
${JSON.stringify(fileSnippets, null, 2)}
Diff summary:
${context.rawDiff?.slice(0, 3000) || 'Full file evaluation'}`;

        const result = await generateWithGemini({
          systemInstruction: QUALITY_AGENT_PROMPT,
          prompt,
          jsonMode: true,
          temperature: 0.2,
        });

        if (result.data) {
          return result.data;
        }
      } catch (err) {
        // Fall back gracefully
      }
    }

    return simulateAgentExecution('quality', context);
  }
}

export default QualityAgent;
