/**
 * PR Sentinel - High-Fidelity Simulation Engine (Mock Mode)
 * Provides deterministic, realistic multi-agent responses for offline evaluation,
 * automated testing, and zero-key demonstrations.
 */

/**
 * Generate simulated agent reasoning and outputs
 * @param {string} agentRole
 * @param {Object} context
 * @returns {Promise<Object>}
 */
export async function simulateAgentExecution(agentRole, context) {
  // Add a slight realistic latency (200-400ms) to emulate thought processing
  await new Promise((resolve) => setTimeout(resolve, 250));

  switch (agentRole) {
    case 'security':
      return simulateSecurityAgent(context);
    case 'quality':
      return simulateQualityAgent(context);
    case 'compliance':
      return simulateComplianceAgent(context);
    case 'patcher':
      return simulatePatcherAgent(context);
    default:
      return {
        summary: `Generic analysis completed for ${agentRole}`,
        findings: [],
        score: 85,
      };
  }
}

function simulateSecurityAgent(context) {
  const secretCount = context.rawSecrets?.length || 0;
  const findings = [];

  if (secretCount > 0) {
    for (const secret of context.rawSecrets) {
      findings.push({
        id: `SEC-SECRET-${findings.length + 1}`,
        type: 'credential_leak',
        severity: 'CRITICAL',
        title: `Exposed ${secret.type} detected in ${secret.file}`,
        description: `Potential unredacted credential matching pattern for ${secret.type} found on line ${secret.line}.`,
        file: secret.file,
        line: secret.line,
        recommendation: 'Remove credential immediately, revoke the exposed key, and move to environment variables.',
      });
    }
  }

  // Check code files for common security flags
  if (context.files) {
    for (const file of context.files) {
      if (file.content && /eval\s*\(|child_process\.exec\s*\(/.test(file.content)) {
        findings.push({
          id: `SEC-EXEC-${findings.length + 1}`,
          type: 'unsafe_execution',
          severity: 'HIGH',
          title: `Unsafe command execution in ${file.path}`,
          description: 'Direct call to eval() or exec() without proper input validation.',
          file: file.path,
          line: 1,
          recommendation: 'Use execFile() with parameterized arguments and strict input sanitization.',
        });
      }
    }
  }

  if (findings.length === 0) {
    findings.push({
      id: 'SEC-OK-1',
      type: 'security_clear',
      severity: 'INFO',
      title: 'Zero High-Risk Vulnerabilities Detected',
      description: 'Zero hardcoded secrets, private keys, or unsafe shell execution patterns detected.',
      file: 'N/A',
      line: 0,
      recommendation: 'Maintain continuous automated security checks in CI/CD pipeline.',
    });
  }

  const criticals = findings.filter(f => f.severity === 'CRITICAL').length;
  const highs = findings.filter(f => f.severity === 'HIGH').length;
  const score = Math.max(10, 100 - (criticals * 40) - (highs * 20));

  return {
    agent: 'SecuritySentinel',
    status: criticals > 0 ? 'FAIL' : (highs > 0 ? 'WARN' : 'PASS'),
    score,
    summary: `Scanned ${context.diffSummary?.filesChanged || 0} files. Found ${secretCount} exposed secrets and ${findings.length} security observations.`,
    findings,
  };
}

function simulateQualityAgent(context) {
  const findings = [];
  const files = context.files || [];

  for (const file of files) {
    if (file.path.endsWith('.js') || file.path.endsWith('.ts') || file.path.endsWith('.py')) {
      // Check for error handling
      if (file.content && !/try\s*\{|\.catch\s*\(|except\s+/.test(file.content)) {
        findings.push({
          id: `QA-ERR-${findings.length + 1}`,
          type: 'resilience',
          severity: 'MEDIUM',
          title: `Missing exception handling in ${file.path}`,
          description: 'Asynchronous calls or I/O operations are performed without structured try/catch or error boundary.',
          file: file.path,
          line: 1,
          recommendation: 'Wrap external calls with robust error handling and descriptive fallback logging.',
        });
      }
    }
  }

  if (findings.length === 0) {
    findings.push({
      id: 'QA-OK-1',
      type: 'clean_architecture',
      severity: 'INFO',
      title: 'Modular Code Architecture Confirmed',
      description: 'Functions maintain single responsibility with clear separation of concerns.',
      file: 'N/A',
      line: 0,
      recommendation: 'Add unit tests to ensure high test coverage across new components.',
    });
  }

  return {
    agent: 'QualityCritic',
    status: findings.some(f => f.severity === 'HIGH') ? 'WARN' : 'PASS',
    score: 90,
    summary: 'Analyzed AST structure, error resilience, and code clarity across modified modules.',
    findings,
  };
}

function simulateComplianceAgent(context) {
  const complianceResults = context.complianceAudit || {
    hasReadme: true,
    hasEnvExample: true,
    hasGitignore: true,
    hasManifest: true,
    isIsolated: true,
    violations: [],
  };

  const findings = [];

  if (!complianceResults.hasReadme) {
    findings.push({
      id: 'COMP-1',
      severity: 'HIGH',
      title: 'Missing Project README.md',
      description: 'Submission must contain a complete README.md derived from template/README.md.',
      recommendation: 'Copy template/README.md and fill in all required sections.',
    });
  }

  if (!complianceResults.hasEnvExample) {
    findings.push({
      id: 'COMP-2',
      severity: 'MEDIUM',
      title: 'Missing .env.example',
      description: 'Environment variables must be documented in a sanitized .env.example file.',
      recommendation: 'Provide .env.example with placeholders.',
    });
  }

  if (!complianceResults.hasManifest) {
    findings.push({
      id: 'COMP-3',
      severity: 'HIGH',
      title: 'Missing Dependency Manifest',
      description: 'No package.json, requirements.txt, or pyproject.toml found in project folder.',
      recommendation: 'Declare all external dependencies in a standard manifest file.',
    });
  }

  if (findings.length === 0) {
    findings.push({
      id: 'COMP-PASS-1',
      severity: 'INFO',
      title: 'Repository Guidelines Fully Satisfied',
      description: 'Directory isolation, template completeness, manifest declaration, and gitignore standards verified.',
      recommendation: 'Ready for upstream pull request submission.',
    });
  }

  return {
    agent: 'ComplianceAuditor',
    status: findings.some(f => f.severity === 'HIGH') ? 'FAIL' : 'PASS',
    score: complianceResults.violations?.length ? 70 : 100,
    summary: `Verified contribution structure against CONTRIBUTING.md checklist. Result: ${findings.length === 1 && findings[0].severity === 'INFO' ? 'Compliant' : 'Needs Attention'}.`,
    findings,
  };
}

function simulatePatcherAgent(context) {
  const patches = [];
  const findings = [
    ...(context.securityFindings || []),
    ...(context.qualityFindings || []),
    ...(context.complianceFindings || []),
  ];

  for (const finding of findings) {
    if (finding.type === 'credential_leak' && finding.file && finding.file !== 'N/A') {
      patches.push({
        targetFile: finding.file,
        description: `Replace hardcoded credential with process.env lookup in ${finding.file}`,
        diff: `--- a/${finding.file}\n+++ b/${finding.file}\n@@ -${finding.line},1 +${finding.line},1 @@\n-const API_KEY = "sk-live-secret-key-12345";\n+const API_KEY = process.env.API_KEY || "";\n`,
      });
    } else if (finding.id === 'COMP-2') {
      patches.push({
        targetFile: '.env.example',
        description: 'Create sanitized .env.example template',
        diff: `--- /dev/null\n+++ b/.env.example\n@@ -0,0 +1,4 @@\n+# Configuration\n+API_KEY=your_api_key_here\n+PORT=3737\n+LOG_LEVEL=info\n`,
      });
    }
  }

  return {
    agent: 'PatchSynthesizer',
    status: 'READY',
    patchCount: patches.length,
    patches,
    summary: `Synthesized ${patches.length} automated corrective patch(es) ready for review or dry-run application.`,
  };
}

export default {
  simulateAgentExecution,
};
