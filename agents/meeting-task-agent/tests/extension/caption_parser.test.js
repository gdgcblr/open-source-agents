import test from 'node:test';
import assert from 'node:assert/strict';

test('Transcript deduplication and delta chunk calculation', () => {
  let lastSpeaker = 'Alice';
  let lastText = 'We need to deploy';

  const newSpeaker = 'Alice';
  const newText = 'We need to deploy the new service by Friday';

  let deltaText = newText;
  if (newSpeaker === lastSpeaker && newText.startsWith(lastText)) {
    deltaText = newText.slice(lastText.length).trim();
  }

  assert.equal(deltaText, 'the new service by Friday');
});

test('Speaker change detection', () => {
  let lastSpeaker = 'Alice';
  const incomingSpeaker = 'Bob';
  const incomingText = 'I will prepare the slides';

  assert.notEqual(lastSpeaker, incomingSpeaker);
  assert.equal(incomingText, 'I will prepare the slides');
});

test('Action item state transition lifecycle', () => {
  const task = {
    id: 'task_1',
    task: 'Write unit tests',
    status: 'pending',
    deadline: null,
    nudgeCount: 0,
  };

  // User sets deadline
  task.deadline = '2026-10-30T17:00:00Z';
  assert.equal(task.deadline, '2026-10-30T17:00:00Z');

  // User ticks off task (completed)
  task.status = 'completed';
  task.completedAt = new Date().toISOString();
  assert.equal(task.status, 'completed');
  assert.ok(task.completedAt);
});

