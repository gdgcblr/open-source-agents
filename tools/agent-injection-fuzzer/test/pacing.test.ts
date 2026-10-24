import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PacingPlugin } from '../src/pacing.js';

test('model calls are spaced by the gap, even when they arrive together', async () => {
  const pacing = new PacingPlugin(40);
  const start = Date.now();
  const finished: number[] = [];
  await Promise.all(
    [0, 1, 2].map(async () => {
      assert.equal(await pacing.beforeModelCallback(), undefined, 'the call is allowed to proceed');
      finished.push(Date.now() - start);
    }),
  );
  finished.sort((a, b) => a - b);
  assert.ok(finished[0]! < 30, `the first call goes at once, took ${finished[0]}ms`);
  assert.ok(finished[2]! >= 75, `the third call waits two gaps, took ${finished[2]}ms`);
});
