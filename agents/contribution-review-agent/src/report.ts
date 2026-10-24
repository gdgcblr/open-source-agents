import type {CheckResult} from './types.js';

export interface Report {
  target: string;
  projectPath: string;
  score: number;
  verdict: string;
  errors: number;
  warnings: number;
  results: CheckResult[];
  aiReview?: string;
}

const ERROR_PENALTY = 15;
const WARNING_PENALTY = 5;

export function buildReport(target: string, projectPath: string, results: CheckResult[]): Report {
  const all = results.flatMap((r) => r.findings);
  const errors = all.filter((f) => f.severity === 'error').length;
  const warnings = all.length - errors;
  const score = Math.max(0, 100 - errors * ERROR_PENALTY - warnings * WARNING_PENALTY);
  const verdict = errors > 0 ? 'Changes requested' : warnings > 0 ? 'Ready, with suggestions' : 'Ready for maintainer review';
  return {target, projectPath, score, verdict, errors, warnings, results};
}

export function renderMarkdown(report: Report): string {
  const lines = [
    `# Contribution Review: \`${report.projectPath || report.target}\``,
    '',
    `**Score:** ${report.score}/100 · **Verdict:** ${report.verdict} · ${report.errors} error(s), ${report.warnings} warning(s)`,
    '',
    '| Check | Result |',
    '| :--- | :--- |',
    ...report.results.map((r) => `| ${r.check} | ${r.skipped ? 'Skipped' : r.passed ? (r.findings.length ? 'Pass (warnings)' : 'Pass') : 'Fail'} |`),
    '',
  ];
  for (const r of report.results) {
    if (r.findings.length === 0) continue;
    lines.push(`### ${r.check}`, '');
    for (const f of r.findings) {
      lines.push(`- **${f.severity.toUpperCase()}** ${f.message}${f.fix ? ` _Fix:_ ${f.fix}` : ''}`);
    }
    lines.push('');
  }
  if (report.aiReview) lines.push('## AI Review (Gemini)', '', report.aiReview, '');
  return lines.join('\n');
}
