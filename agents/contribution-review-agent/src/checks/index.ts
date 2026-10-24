import {checkReadme} from './readme.js';
import {scanSecrets} from './secrets.js';
import {checkScope} from './scope.js';
import {checkStructure} from './structure.js';
import {buildReport, type Report} from '../report.js';
import type {ProjectSource} from '../types.js';

export async function runAllChecks(source: ProjectSource): Promise<Report> {
  const results = [
    checkStructure(source.projectPath, source.files),
    await scanSecrets(source.files, (p) => source.readFile(p)),
    checkReadme(await source.readFile('README.md')),
    checkScope(source.projectPath, source.changedFiles),
  ];
  return buildReport(source.label, source.projectPath, results);
}
