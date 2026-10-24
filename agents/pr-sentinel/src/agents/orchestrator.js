/**
 * PR Sentinel - Multi-Agent Orchestrator
 * Coordinates agent handoffs, pipeline phases, state aggregation, and PR review synthesis.
 */

import { getGitInfo, getGitDiff, parseUnifiedDiff, readDirectoryFiles } from '../tools/git.js';
import { SecurityAgent } from './security.js';
import { QualityAgent } from './quality.js';
import { ComplianceAgent } from './compliance.js';
import { PatcherAgent } from './patcher.js';
import { BlastAgent } from './blast.js';

export class Orchestrator {
  constructor(options = {}) {
    this.options = options;
    this.securityAgent = new SecurityAgent();
    this.qualityAgent = new QualityAgent();
    this.complianceAgent = new ComplianceAgent();
    this.patcherAgent = new PatcherAgent();
    this.blastAgent = new BlastAgent();
    this.events = [];
    this.onProgress = options.onProgress || (() => {});
  }

  logStep(phase, agent, message) {
    const event = {
      timestamp: new Date().toISOString(),
      phase,
      agent,
      message,
    };
    this.events.push(event);
    this.onProgress(event);
  }

  /**
   * Run the complete multi-agent review pipeline
   * @param {Object} targetOptions
   * @param {string} [targetOptions.targetDir]
   * @param {string} [targetOptions.baseBranch]
   * @param {boolean} [targetOptions.staged]
   * @param {string} [targetOptions.rawDiff]
   * @returns {Promise<Object>} Full triage and review report
   */
  async runReview({ targetDir = '.', baseBranch, staged = false, rawDiff = null } = {}) {
    const startTime = Date.now();
    this.logStep('INIT', 'Orchestrator', 'Initializing PR Sentinel Multi-Agent Review Pipeline');

    // 1. Gather Context & Diffs
    const gitInfo = getGitInfo(targetDir);
    let diffText = rawDiff || getGitDiff({ cwd: targetDir, base: baseBranch, staged });
    let diffFiles = parseUnifiedDiff(diffText);
    let projectFiles = [];

    // If diff is empty, inspect directory files directly
    if (diffFiles.length === 0) {
      this.logStep('DISCOVERY', 'Orchestrator', `Scanning local files in ${targetDir}`);
      projectFiles = readDirectoryFiles(targetDir);
    } else {
      projectFiles = diffFiles.map(df => ({
        path: df.path,
        content: df.rawBlock,
      }));
    }

    const context = {
      targetDir,
      gitInfo,
      rawDiff: diffText,
      diffSummary: {
        filesChanged: diffFiles.length || projectFiles.length,
        files: diffFiles,
      },
      files: projectFiles,
    };

    // Phase 1: Security Sentinel
    this.logStep('PHASE_1', 'SecuritySentinel', 'Auditing for exposed credentials and dangerous code patterns');
    const securityStart = Date.now();
    const securityResults = await this.securityAgent.audit(context);
    const securityDuration = Date.now() - securityStart;

    // Phase 2: Quality Critic
    this.logStep('PHASE_2', 'QualityCritic', 'Evaluating code architecture, error resilience, and maintainability');
    const qualityStart = Date.now();
    const qualityResults = await this.qualityAgent.audit({
      ...context,
      securityResults,
    });
    const qualityDuration = Date.now() - qualityStart;

    // Phase 3: Compliance Auditor
    this.logStep('PHASE_3', 'ComplianceAuditor', 'Verifying open-source repository guidelines & directory isolation');
    const complianceStart = Date.now();
    const complianceResults = await this.complianceAgent.audit({
      ...context,
      securityResults,
      qualityResults,
    });
    const complianceDuration = Date.now() - complianceStart;

    // Phase 4: Patch Synthesizer
    this.logStep('PHASE_4', 'PatchSynthesizer', 'Synthesizing automated corrective diff patches');
    const patcherStart = Date.now();
    const patcherResults = await this.patcherAgent.synthesize({
      ...context,
      securityResults,
      qualityResults,
      complianceResults,
    });
    const patcherDuration = Date.now() - patcherStart;

    // Phase 5: Blast Radius Predictor
    this.logStep('PHASE_5', 'BlastRadiusPredictor', 'Simulating downstream call-graph blast radius & regression breakages');
    const blastStart = Date.now();
    const allProjectFiles = readDirectoryFiles(targetDir);
    const blastResults = await this.blastAgent.forecast({
      ...context,
      allProjectFiles,
    });
    const blastDuration = Date.now() - blastStart;

    // Phase 6: Synthesis & PR Verdict Calculation
    this.logStep('SYNTHESIS', 'Orchestrator', 'Synthesizing executive PR readiness score and markdown review');

    const totalDuration = Date.now() - startTime;
    const compositeScore = Math.round(
      (securityResults.score * 0.40) +
      (complianceResults.score * 0.30) +
      (qualityResults.score * 0.20) +
      (Math.max(0, 100 - (blastResults.blastScore || 0)) * 0.10)
    );

    let verdict = 'APPROVED';
    if (securityResults.status === 'FAIL' || complianceResults.status === 'FAIL' || blastResults.status === 'CRITICAL') {
      verdict = 'REQUEST_CHANGES';
    } else if (securityResults.status === 'WARN' || complianceResults.status === 'WARN' || blastResults.status === 'WARN') {
      verdict = 'NEEDS_REVIEW';
    }

    const report = {
      metadata: {
        timestamp: new Date().toISOString(),
        totalDurationMs: totalDuration,
        git: gitInfo,
        targetDir,
        filesScanned: context.diffSummary.filesChanged,
      },
      verdict,
      compositeScore,
      agents: {
        security: {
          ...securityResults,
          durationMs: securityDuration,
        },
        quality: {
          ...qualityResults,
          durationMs: qualityDuration,
        },
        compliance: {
          ...complianceResults,
          durationMs: complianceDuration,
        },
        patcher: {
          ...patcherResults,
          durationMs: patcherDuration,
        },
        blast: {
          ...blastResults,
          durationMs: blastDuration,
        },
      },
      events: this.events,
      markdownReview: this.generateMarkdownReview({
        verdict,
        compositeScore,
        gitInfo,
        securityResults,
        qualityResults,
        complianceResults,
        patcherResults,
        blastResults,
      }),
    };

    this.logStep('COMPLETE', 'Orchestrator', `Review finished. Verdict: ${verdict} (Score: ${compositeScore}/100)`);
    return report;
  }

  /**
   * Format findings into a professional GitHub PR review comment
   */
  generateMarkdownReview({
    verdict,
    compositeScore,
    gitInfo,
    securityResults,
    qualityResults,
    complianceResults,
    patcherResults,
    blastResults = {},
  }) {
    const verdictEmoji = verdict === 'APPROVED' ? '✅' : (verdict === 'NEEDS_REVIEW' ? '⚠️' : '❌');

    const lines = [
      `# ${verdictEmoji} PR Sentinel Automated Review Report`,
      '',
      `> **Verdict:** \`${verdict}\` | **Readiness Score:** \`${compositeScore}/100\` | **Branch:** \`${gitInfo?.branch || 'unknown'}\``,
      '',
      '---',
      '',
      '### 🛡️ Agent Executive Summary',
      '',
      '| Agent | Status | Score | Primary Focus |',
      '| :--- | :---: | :---: | :--- |',
      `| **SecuritySentinel** | \`${securityResults.status}\` | ${securityResults.score}/100 | Secrets, dangerous code & API safety |`,
      `| **ComplianceAuditor** | \`${complianceResults.status}\` | ${complianceResults.score}/100 | CONTRIBUTING.md checklist & isolation |`,
      `| **QualityCritic** | \`${qualityResults.status}\` | ${qualityResults.score}/100 | Architecture, resilience & modularity |`,
      `| **BlastRadiusPredictor** | \`${blastResults.status || 'PASS'}\` | Blast: ${blastResults.blastScore || 0}% | Downstream regressions & caller impact |`,
      '',
      '---',
      '',
      '### 💥 Blast Radius & Downstream Impact Radar',
      '',
      `> **Containment Verdict:** \`${blastResults.containmentVerdict || 'ISOLATED'}\` | **Contract Integrity:** \`${blastResults.contractIntegrity || 'STABLE'}\``,
      '',
      blastResults.summary || 'No external downstream callers affected.',
      '',
    ];

    if (blastResults.downstreamImpacts && blastResults.downstreamImpacts.length > 0) {
      lines.push('**Downstream Untouched Callers at Risk:**');
      for (const impact of blastResults.downstreamImpacts) {
        lines.push(`- ⚠️ **\`${impact.impactedFile}\`** (depends on \`${impact.brokenSymbol}\`)`);
        lines.push(`  - *Predicted Failure:* ${impact.predictedFailure}`);
        lines.push(`  - *Fix:* ${impact.preventionFix}`);
      }
      lines.push('');
    }

    lines.push('---', '', '### 🔍 Key Findings & Recommendations', '');

    const allFindings = [
      ...(securityResults.findings || []),
      ...(complianceResults.findings || []),
      ...(qualityResults.findings || []),
    ];

    if (allFindings.length === 0 || (allFindings.length === 1 && allFindings[0].severity === 'INFO')) {
      lines.push('🎉 **No blocking issues detected.** All security, compliance, and code quality checks passed.');
    } else {
      for (const finding of allFindings) {
        if (finding.severity === 'INFO') continue;
        const badge = finding.severity === 'CRITICAL' ? '🔴 **CRITICAL**' :
                      finding.severity === 'HIGH' ? '🟠 **HIGH**' :
                      finding.severity === 'MEDIUM' ? '🟡 **MEDIUM**' : '🔵 **LOW**';

        lines.push(`- ${badge} - **${finding.title}**`);
        if (finding.file && finding.file !== 'N/A') {
          lines.push(`  - *Location:* \`${finding.file}${finding.line ? `:${finding.line}` : ''}\``);
        }
        lines.push(`  - *Description:* ${finding.description}`);
        if (finding.recommendation) {
          lines.push(`  - *Fix:* ${finding.recommendation}`);
        }
        lines.push('');
      }
    }

    if (patcherResults.patches && patcherResults.patches.length > 0) {
      lines.push('---', '', '### 🛠️ Automated Corrective Patches Available', '');
      for (const patch of patcherResults.patches) {
        lines.push(`<details><summary><b>Patch for <code>${patch.targetFile}</code>: ${patch.title || 'Automated fix'}</b></summary>`, '', '```diff');
        lines.push(patch.diff.trim());
        lines.push('```', '', '</details>', '');
      }
    }

    lines.push('---', '*Generated autonomously by [PR Sentinel](agents/pr-sentinel) powered by Gemini.*');
    return lines.join('\n');
  }
}

export default Orchestrator;
