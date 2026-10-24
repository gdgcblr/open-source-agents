import {type CheckResult, type Finding, toResult} from '../types.js';

const KEBAB_CASE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const GENERIC_NAMES = new Set([
  'agent', 'tool', 'project', 'test', 'demo', 'helper', 'example', 'sample',
  'my-agent', 'my-tool', 'my-project', 'final-project', 'final-test',
]);
const MANIFESTS = [
  'package.json', 'requirements.txt', 'pyproject.toml', 'Pipfile', 'go.mod', 'Cargo.toml',
  'pom.xml', 'build.gradle', 'build.gradle.kts', 'Gemfile', 'composer.json',
];

export function checkStructure(projectPath: string, files: string[]): CheckResult {
  const findings: Finding[] = [];
  const [category, slug, ...rest] = projectPath.split('/');

  if (!['agents', 'tools'].includes(category) || !slug || rest.length > 0) {
    findings.push({
      severity: 'error',
      message: `Project folder \`${projectPath || '(none)'}\` is not directly under \`agents/\` or \`tools/\`.`,
      fix: 'Move the project to `agents/<project-slug>/` or `tools/<project-slug>/`.',
    });
  }
  if (slug && !KEBAB_CASE.test(slug)) {
    findings.push({
      severity: 'error',
      message: `Folder name \`${slug}\` is not lowercase kebab-case.`,
      fix: 'Rename it, e.g. `meeting-summarizer`.',
    });
  }
  if (slug && GENERIC_NAMES.has(slug)) {
    findings.push({
      severity: 'error',
      message: `Folder name \`${slug}\` is too generic.`,
      fix: 'Pick a name that describes what the project does.',
    });
  }

  const topLevel = new Set(files.filter((f) => !f.includes('/')));
  if (!topLevel.has('README.md')) {
    findings.push({severity: 'error', message: '`README.md` is missing.', fix: 'Copy `template/README.md` and fill it in.'});
  }
  if (!MANIFESTS.some((m) => topLevel.has(m))) {
    findings.push({
      severity: 'error',
      message: 'No dependency manifest found.',
      fix: `Add one of: ${MANIFESTS.slice(0, 5).join(', ')}.`,
    });
  }
  if (!topLevel.has('.gitignore')) {
    findings.push({severity: 'warning', message: '`.gitignore` is missing.', fix: 'Copy `template/.gitignore`.'});
  }
  if (!topLevel.has('.env.example')) {
    findings.push({
      severity: 'warning',
      message: '`.env.example` is missing.',
      fix: 'Copy `template/.env.example` if the project uses environment variables.',
    });
  }
  return toResult('Structure & naming', findings);
}
