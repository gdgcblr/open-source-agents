import {type CheckResult, type Finding, toResult} from '../types.js';

const PROJECT_DIR = /^((?:agents|tools)\/[^/]+)\//;
const INDEX_FILES = new Set(['agents/README.md', 'tools/README.md']);

/** Picks the project folder that most of the changed files belong to. */
export function detectProjectPath(paths: string[]): string | null {
  const counts = new Map<string, number>();
  for (const p of paths) {
    const dir = p.match(PROJECT_DIR)?.[1];
    if (dir) counts.set(dir, (counts.get(dir) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

export function checkScope(projectPath: string, changedFiles?: string[]): CheckResult {
  if (!changedFiles) {
    return {check: 'PR scope', passed: true, skipped: 'Only checked when reviewing a pull request.', findings: []};
  }
  if (!projectPath) {
    return toResult('PR scope', [{
      severity: 'error',
      message: 'The PR does not add or change anything under `agents/<slug>/` or `tools/<slug>/`.',
      fix: 'Put the project in its own folder under `agents/` or `tools/`.',
    }]);
  }

  const findings: Finding[] = [];
  const otherProjects = new Set<string>();
  for (const file of changedFiles) {
    if (file.startsWith(`${projectPath}/`) || INDEX_FILES.has(file)) continue;
    const dir = file.match(PROJECT_DIR)?.[1];
    if (dir) {
      otherProjects.add(dir);
    } else {
      findings.push({
        severity: 'error',
        message: `Changes \`${file}\`, which is outside the project folder.`,
        fix: 'Revert this file. PRs may only touch the project folder and one index row.',
      });
    }
  }
  for (const dir of otherProjects) {
    findings.push({
      severity: 'error',
      message: `Also changes another project: \`${dir}/\`.`,
      fix: 'Submit one project per PR and do not edit other contributors\' folders.',
    });
  }
  return toResult('PR scope', findings);
}
