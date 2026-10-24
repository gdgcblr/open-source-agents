import test from 'node:test';
import assert from 'node:assert/strict';
import { auditProjectCompliance } from '../src/tools/compliance.js';
import path from 'node:path';

test('compliance auditor verifies valid kebab-case folder name', () => {
  const result = auditProjectCompliance('.');
  // Directory should not flag naming violation if kebab-case
  const namingViolations = result.violations.filter(v => v.rule === 'NAMING_CONVENTION');
  assert.equal(namingViolations.length, 0);
});

test('compliance auditor checks presence of package manifest', () => {
  const result = auditProjectCompliance('.');
  assert.equal(result.hasManifest, true);
  assert.equal(result.manifestType, 'package.json');
});

test('compliance auditor flags isolation violations when PR modifies outside files', () => {
  const currentDir = process.cwd();
  const changedFiles = [
    'agents/pr-sentinel/src/cli.js',
    'agents/other-project/index.py', // outside project!
  ];
  const result = auditProjectCompliance('.', changedFiles);
  assert.equal(result.isIsolated, false);
  assert.equal(result.violations.some(v => v.rule === 'CROSS_PROJECT_POLLUTION'), true);
});

test('compliance auditor allows updating root agents/README.md index', () => {
  const changedFiles = [
    'agents/pr-sentinel/src/cli.js',
    'agents/README.md', // allowed index modification
  ];
  const result = auditProjectCompliance('.', changedFiles);
  assert.equal(result.isIsolated, true);
});
