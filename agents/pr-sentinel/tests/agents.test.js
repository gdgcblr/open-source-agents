import test from 'node:test';
import assert from 'node:assert/strict';
import { Orchestrator } from '../src/agents/orchestrator.js';
import { config } from '../src/config.js';

test('Orchestrator executes full multi-agent pipeline deterministically in mock mode', async () => {
  config.mockMode = true;

  const orchestrator = new Orchestrator();
  const sampleDiff = `diff --git a/agents/demo/app.js b/agents/demo/app.js
--- /dev/null
+++ b/agents/demo/app.js
@@ -0,0 +1,5 @@
+const SECRET = "AIzaSyB8z9X1234567890123456789012345678";
+eval("dangerous();");
+`;

  const report = await orchestrator.runReview({
    targetDir: '.',
    rawDiff: sampleDiff,
  });

  assert.equal(typeof report.compositeScore, 'number');
  assert.equal(report.verdict === 'REQUEST_CHANGES' || report.verdict === 'FAIL', true);
  assert.equal(report.agents.security.status, 'FAIL');
  assert.equal(report.agents.patcher.patches.length >= 1, true);
  assert.equal(report.markdownReview.includes('PR Sentinel Automated Review Report'), true);
});

test('Orchestrator generates clean markdown review report', async () => {
  config.mockMode = true;
  const orchestrator = new Orchestrator();

  const report = await orchestrator.runReview({ targetDir: '.' });
  assert.equal(typeof report.markdownReview, 'string');
  assert.equal(report.markdownReview.includes('Agent Executive Summary'), true);
  assert.equal(report.markdownReview.includes('SecuritySentinel'), true);
  assert.equal(report.markdownReview.includes('ComplianceAuditor'), true);
});
