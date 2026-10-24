import {type CheckResult, type Finding, toResult} from '../types.js';

// Mirrors the section headings in template/README.md.
export const REQUIRED_SECTIONS: {title: string; match: RegExp}[] = [
  {title: 'Overview', match: /overview/i},
  {title: 'Technical Stack', match: /tech(?:nical)? stack/i},
  {title: 'Architecture & Data Flow', match: /architecture|data flow/i},
  {title: 'Prerequisites', match: /prerequisites/i},
  {title: 'Installation & Setup', match: /install|setup/i},
  {title: 'Configuration & Environment Variables', match: /configuration|environment/i},
  {title: 'How to Run', match: /how to run|usage/i},
  {title: 'Example Input & Output', match: /example/i},
  {title: 'How to Test', match: /test/i},
  {title: 'Known Limitations', match: /limitation/i},
  {title: 'Security & Privacy Considerations', match: /security|privacy/i},
  {title: 'License', match: /licen[cs]e/i},
];

const TEMPLATE_PLACEHOLDERS = [
  '[Project Name]',
  '[One-sentence summary',
  'Feature 1: Brief description',
  'Explain what specific problem',
  '[Language Runtime',
  '[Required API keys',
  'Analyze the repository structure of gdgcblr/open-source-agents',
  'e.g., Rate limits on free-tier APIs',
  'Specify the license for this subproject',
];
const UNFILLED_THRESHOLD = 3;

export function checkReadme(readme: string | null): CheckResult {
  if (readme === null) {
    return toResult('README completeness', [
      {severity: 'error', message: '`README.md` could not be read.', fix: 'Copy `template/README.md` and fill it in.'},
    ]);
  }
  const findings: Finding[] = [];
  const headings = [...readme.matchAll(/^#{2,3}\s+(.+)$/gm)].map((m) => m[1]);

  for (const section of REQUIRED_SECTIONS) {
    if (!headings.some((h) => section.match.test(h))) {
      findings.push({
        severity: 'error',
        message: `Section **${section.title}** is missing.`,
        fix: 'Add it, or write "N/A" with a short reason.',
      });
    }
  }
  const lines = readme.split('\n');
  const leftoverLines = TEMPLATE_PLACEHOLDERS
    .map((p) => lines.findIndex((line) => line.includes(p)) + 1)
    .filter((n) => n > 0)
    .sort((a, b) => a - b);
  if (leftoverLines.length > 0) {
    findings.push({
      // A handful of leftovers is an oversight; many means the template was never filled in.
      severity: leftoverLines.length >= UNFILLED_THRESHOLD ? 'error' : 'warning',
      message: `${leftoverLines.length} template placeholder(s) left in README.md (lines ${leftoverLines.join(', ')}).`,
      fix: 'Replace them with content specific to your project.',
    });
  }
  return toResult('README completeness', findings);
}
