import assert from 'node:assert/strict';
import test from 'node:test';

import {validateScenarios} from '../src/validation.ts';

const requirements = [
  {id: 'REQ-001', text: 'User can request a password reset.'},
  {id: 'REQ-002', text: 'Reset links expire after 15 minutes.'},
];

const scenario = (overrides = {}) => ({
  id: 'TC-001',
  title: 'Request a reset with a valid account',
  category: 'happy_path',
  priority: 'P1',
  preconditions: ['A registered account exists.'],
  steps: ['Enter the registered email.', 'Submit the form.'],
  expectedResult: 'A reset link is sent.',
  requirementIds: ['REQ-001'],
  ...overrides,
});

test('reports requirements that have no linked scenarios', () => {
  const result = validateScenarios(requirements, [scenario()]);
  assert.equal(result.valid, false);
  assert.deepEqual(result.uncoveredRequirementIds, ['REQ-002']);
});

test('accepts complete structurally valid scenario coverage', () => {
  const result = validateScenarios(requirements, [
    scenario(),
    scenario({
      id: 'TC-002',
      title: 'Reject an expired reset link',
      category: 'boundary',
      requirementIds: ['REQ-002'],
    }),
  ]);
  assert.equal(result.valid, true);
  assert.deepEqual(result.issues, []);
});

test('detects duplicate IDs, duplicate titles, and unknown requirement references', () => {
  const result = validateScenarios(requirements, [
    scenario(),
    scenario({requirementIds: ['REQ-404']}),
  ]);
  assert.equal(result.valid, false);
  assert.ok(result.issues.some((issue) => issue.includes('duplicate scenario ID')));
  assert.ok(result.issues.some((issue) => issue.includes('duplicate scenario title')));
  assert.ok(result.issues.some((issue) => issue.includes('unknown requirement ID')));
});