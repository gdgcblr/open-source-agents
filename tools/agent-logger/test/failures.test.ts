import assert from 'node:assert/strict';
import test from 'node:test';
import { describeFailure } from '../src/adk-failures.js';

test('provider failures expose static, safe categories and corrective messages', () => {
  const cases = [
    [401, 'authentication_failed'],
    [403, 'access_denied'],
    [404, 'model_unavailable'],
    [429, 'quota_exceeded'],
    [503, 'provider_unavailable'],
  ] as const;
  for (const [status, category] of cases) {
    const failure = describeFailure(
      new Error(
        JSON.stringify({ error: { code: status, message: 'secret-provider-value' } }),
      ),
    );
    assert.equal(failure.errorCategory, category);
    assert.equal(failure.httpStatus, status);
    assert.ok(!JSON.stringify(failure).includes('secret-provider-value'));
  }
  assert.equal(
    describeFailure({ errorCode: 'RESOURCE_EXHAUSTED' }).errorCategory,
    'quota_exceeded',
  );
  assert.equal(describeFailure({ errorCode: 'SAFETY' }).errorCategory, 'content_blocked');
  assert.equal(
    describeFailure(new Error('fetch failed')).errorCategory,
    'network_failed',
  );
});
