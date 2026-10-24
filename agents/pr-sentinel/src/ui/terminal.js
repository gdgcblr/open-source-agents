/**
 * PR Sentinel - Terminal UI Utilities
 * Native ANSI styling, banners, spinners, progress meters, and table rendering.
 */

export const colors = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  italic: '\x1b[3m',
  underline: '\x1b[4m',

  // Colors
  black: '\x1b[30m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  white: '\x1b[37m',

  // Bright
  brightRed: '\x1b[91m',
  brightGreen: '\x1b[92m',
  brightYellow: '\x1b[93m',
  brightBlue: '\x1b[94m',
  brightMagenta: '\x1b[95m',
  brightCyan: '\x1b[96m',
  brightWhite: '\x1b[97m',

  // Background
  bgRed: '\x1b[41m',
  bgGreen: '\x1b[42m',
  bgYellow: '\x1b[43m',
  bgBlue: '\x1b[44m',
  bgCyan: '\x1b[46m',
};

export function banner() {
  console.log(`
${colors.brightCyan}${colors.bold}  ██████╗ ██████╗     ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗     
  ██╔══██╗██╔══██╗    ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     
  ██████╔╝██████╔╝    ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     
  ██╔═══╝ ██╔══██╗    ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     
  ██║     ██║  ██║    ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗
  ╚═╝     ╚═╝  ╚═╝    ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝${colors.reset}
  ${colors.dim}Autonomous Multi-Agent PR Review, Security Triage, and Auto-Patch System${colors.reset}
  ${colors.cyan}Powered by Google Gemini 2.5 & Google Developer Groups${colors.reset}
`);
}

export function badge(status) {
  switch (status) {
    case 'PASS':
    case 'APPROVED':
      return `${colors.bgGreen}${colors.black}${colors.bold} PASS ${colors.reset}`;
    case 'WARN':
    case 'NEEDS_REVIEW':
      return `${colors.bgYellow}${colors.black}${colors.bold} WARN ${colors.reset}`;
    case 'FAIL':
    case 'REQUEST_CHANGES':
      return `${colors.bgRed}${colors.white}${colors.bold} FAIL ${colors.reset}`;
    default:
      return `${colors.bgBlue}${colors.white}${colors.bold} ${status} ${colors.reset}`;
  }
}

export function severityBadge(severity) {
  switch (severity) {
    case 'CRITICAL':
      return `${colors.brightRed}${colors.bold}[CRITICAL]${colors.reset}`;
    case 'HIGH':
      return `${colors.red}${colors.bold}[HIGH]${colors.reset}`;
    case 'MEDIUM':
      return `${colors.yellow}[MEDIUM]${colors.reset}`;
    case 'LOW':
      return `${colors.blue}[LOW]${colors.reset}`;
    default:
      return `${colors.cyan}[INFO]${colors.reset}`;
  }
}

export function printHeader(text) {
  console.log(`\n${colors.bold}${colors.brightWhite}==> ${text}${colors.reset}`);
}

export function printStep(agent, message) {
  console.log(`  ${colors.cyan}▸${colors.reset} ${colors.bold}[${agent}]${colors.reset} ${message}`);
}

export function printReport(report) {
  console.log(`${colors.bold}Target Directory:${colors.reset} ${report.metadata.targetDir}`);
  console.log(`${colors.bold}Branch:${colors.reset} ${report.metadata.git.branch}  |  ${colors.bold}Commit:${colors.reset} ${report.metadata.git.headCommit}`);
  console.log(`${colors.bold}Files Scanned:${colors.reset} ${report.metadata.filesScanned}  |  ${colors.bold}Duration:${colors.reset} ${report.metadata.totalDurationMs}ms\n`);

  console.log(`${colors.bold}PR READINESS VERDICT:${colors.reset} ${badge(report.verdict)}  (Score: ${report.compositeScore}/100)`);
  console.log('────────────────────────────────────────────────────────────────────────────');

  // Agent Status Summary Table
  console.log(`\n${colors.bold}AGENT EXECUTION SUMMARY:${colors.reset}`);
  const agents = report.agents;
  console.log(`  • ${colors.bold}SecuritySentinel${colors.reset}:   ${badge(agents.security.status)} Score: ${agents.security.score}/100 (${agents.security.durationMs}ms)`);
  console.log(`    ${colors.dim}${agents.security.summary}${colors.reset}`);

  console.log(`  • ${colors.bold}ComplianceAuditor${colors.reset}:  ${badge(agents.compliance.status)} Score: ${agents.compliance.score}/100 (${agents.compliance.durationMs}ms)`);
  console.log(`    ${colors.dim}${agents.compliance.summary}${colors.reset}`);

  console.log(`  • ${colors.bold}QualityCritic${colors.reset}:      ${badge(agents.quality.status)} Score: ${agents.quality.score}/100 (${agents.quality.durationMs}ms)`);
  console.log(`    ${colors.dim}${agents.quality.summary}${colors.reset}`);

  if (agents.patcher.patches && agents.patcher.patches.length > 0) {
    console.log(`  • ${colors.bold}PatchSynthesizer${colors.reset}:   ${colors.brightGreen}${agents.patcher.patches.length} patch(es) generated${colors.reset}`);
  }

  // Key Findings
  const allFindings = [
    ...(agents.security.findings || []),
    ...(agents.compliance.findings || []),
    ...(agents.quality.findings || []),
  ];

  const significantFindings = allFindings.filter(f => f.severity !== 'INFO');

  if (significantFindings.length > 0) {
    console.log(`\n${colors.bold}KEY FINDINGS (${significantFindings.length}):${colors.reset}`);
    for (const f of significantFindings) {
      console.log(`  ${severityBadge(f.severity)} ${colors.bold}${f.title}${colors.reset}`);
      if (f.file && f.file !== 'N/A') {
        console.log(`    ${colors.dim}Location:${colors.reset} ${f.file}${f.line ? `:${f.line}` : ''}`);
      }
      console.log(`    ${colors.dim}Issue:${colors.reset}    ${f.description}`);
      if (f.recommendation) {
        console.log(`    ${colors.brightGreen}Action:${colors.reset}   ${f.recommendation}`);
      }
      console.log();
    }
  } else {
    console.log(`\n${colors.brightGreen}✔ Zero critical vulnerabilities or compliance violations detected!${colors.reset}\n`);
  }

  // Patches preview
  if (agents.patcher.patches && agents.patcher.patches.length > 0) {
    console.log(`${colors.bold}AVAILABLE AUTO-PATCHES:${colors.reset}`);
    for (const p of agents.patcher.patches) {
      console.log(`  ${colors.brightCyan}• ${p.targetFile}:${colors.reset} ${p.title || p.description}`);
    }
    console.log(`\n  ${colors.dim}(View or apply patches using the web dashboard or markdown review)${colors.reset}`);
  }

  console.log('\n────────────────────────────────────────────────────────────────────────────\n');
}

export default {
  colors,
  banner,
  badge,
  severityBadge,
  printHeader,
  printStep,
  printReport,
};
