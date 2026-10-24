import test from 'node:test';
import assert from 'node:assert/strict';
import { extractExportedSymbols, findDownstreamCallers, calculateBlastRadius } from '../src/tools/blast.js';
import { BlastAgent } from '../src/agents/blast.js';

test('extractExportedSymbols parses named exports, async functions, and classes', () => {
  const code = `
    export const API_URL = "https://api.example.com";
    export async function fetchMetrics(id) {}
    export class PipelineManager {}
    export { helper, utils as utilityService };
  `;

  const symbols = extractExportedSymbols(code);
  assert.equal(symbols.includes('API_URL'), true);
  assert.equal(symbols.includes('fetchMetrics'), true);
  assert.equal(symbols.includes('PipelineManager'), true);
  assert.equal(symbols.includes('utilityService'), true);
});

test('findDownstreamCallers discovers untouched files depending on modified symbols', () => {
  const allFiles = [
    {
      path: 'src/routes/api.js',
      content: 'import { fetchMetrics } from "../services/metrics.js"; const data = fetchMetrics("tenant-1");',
    },
    {
      path: 'src/models/user.js',
      content: 'export class User { constructor() {} }',
    },
    {
      path: 'tests/metrics.test.js',
      content: 'test("metrics works", () => { fetchMetrics(123); });',
    },
  ];

  const changedPaths = ['src/services/metrics.js'];
  const modifiedSymbols = ['fetchMetrics'];

  const callers = findDownstreamCallers(modifiedSymbols, allFiles, changedPaths);
  assert.equal(callers.length, 2);
  const routeCaller = callers.find(c => c.file === 'src/routes/api.js');
  assert.equal(Boolean(routeCaller), true);
  assert.equal(routeCaller.references.includes('fetchMetrics'), true);
  assert.equal(routeCaller.riskLevel, 'PRODUCTION_REGRESSION_RISK');

  const testCaller = callers.find(c => c.file === 'tests/metrics.test.js');
  assert.equal(testCaller.riskLevel, 'VERIFICATION_DEBT');
});

test('calculateBlastRadius penalizes untested downstream callers', () => {
  const lowRisk = calculateBlastRadius({
    totalFiles: 20,
    impactedFilesCount: 1,
    modifiedSymbolsCount: 1,
    hasTestCoverageUpdates: true,
  });

  const highRisk = calculateBlastRadius({
    totalFiles: 20,
    impactedFilesCount: 8,
    modifiedSymbolsCount: 4,
    hasTestCoverageUpdates: false,
  });

  assert.equal(lowRisk.score < highRisk.score, true);
  assert.equal(highRisk.containmentCategory === 'CATASTROPHIC_POTENTIAL' || highRisk.containmentCategory === 'MODERATE_DOWNSTREAM_RIPPLE', true);
});

test('BlastAgent forecasts regressions deterministically in simulation mode', async () => {
  const agent = new BlastAgent();
  const context = {
    files: [
      {
        path: 'src/core/auth.js',
        content: 'export function verifyToken(jwt) { return true; }',
      },
    ],
    allProjectFiles: [
      {
        path: 'src/core/auth.js',
        content: 'export function verifyToken(jwt) { return true; }',
      },
      {
        path: 'src/middleware/guard.js',
        content: 'const ok = verifyToken(req.headers.auth);',
      },
    ],
  };

  const report = await agent.forecast(context);
  assert.equal(report.agent, 'BlastRadiusPredictor');
  assert.equal(typeof report.blastScore, 'number');
  assert.equal(report.downstreamCallers.length, 1);
  assert.equal(report.downstreamImpacts.length, 1);
});
