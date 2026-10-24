import test from 'node:test';
import assert from 'node:assert/strict';
import { parseUnifiedDiff } from '../src/tools/git.js';
import { createLineReplacementPatch, generateFixPatches } from '../src/tools/patcher.js';

test('parseUnifiedDiff correctly extracts changed files and additions/deletions', () => {
  const sampleDiff = `diff --git a/src/index.js b/src/index.js
index 1234567..89abcdef 100644
--- a/src/index.js
+++ b/src/index.js
@@ -1,3 +1,4 @@
-const old = 1;
+const newVar = 2;
+const extra = 3;
`;

  const files = parseUnifiedDiff(sampleDiff);
  assert.equal(files.length, 1);
  assert.equal(files[0].path, 'src/index.js');
  assert.equal(files[0].additions, 2);
  assert.equal(files[0].deletions, 1);
  assert.equal(files[0].hunks.length, 1);
});

test('createLineReplacementPatch formats valid git unified diff', () => {
  const patch = createLineReplacementPatch({
    filePath: 'src/config.js',
    lineNum: 10,
    oldLine: 'const KEY = "12345";',
    newLine: 'const KEY = process.env.KEY;',
  });

  assert.equal(patch.includes('--- a/src/config.js'), true);
  assert.equal(patch.includes('+++ b/src/config.js'), true);
  assert.equal(patch.includes('@@ -10,1 +10,1 @@'), true);
  assert.equal(patch.includes('-const KEY = "12345";'), true);
  assert.equal(patch.includes('+const KEY = process.env.KEY;'), true);
});

test('generateFixPatches generates patches for credential leaks', () => {
  const dummyKey = ['AIza', 'Sy', 'TEST', 'FAKE', '1234567890123456789012345'].join('');
  const issues = [
    {
      type: 'gemini_api_key',
      file: 'src/main.js',
      line: 5,
      context: `const API_KEY = "${dummyKey}";`,
    },
  ];

  const patches = generateFixPatches(issues);
  assert.equal(patches.length, 1);
  assert.equal(patches[0].targetFile, 'src/main.js');
  assert.equal(patches[0].diff.includes('process.env.API_KEY'), true);
});
