import { test } from 'node:test'
import assert from 'node:assert/strict'
import { padMs, estimateTotalSeconds } from '../src/engine/timing.mjs'
import { estimateSpokenSeconds } from '../src/engine/tts.mjs'

test('a scene holds for the rest of its narration plus the tail', () => {
  // 9s of narration, steps took 3s, 750ms tail -> hold 6.75s more.
  assert.equal(padMs(9, 3000, 750), 6750)
})

test('a scene whose steps out-run the narration does not wait', () => {
  assert.equal(padMs(4, 9000, 750), 0)
})

test('the tail still applies when the steps finish exactly on the voice', () => {
  assert.equal(padMs(5, 5000, 750), 750)
})

test('a silent scene still holds for the tail', () => {
  assert.equal(padMs(0, 0, 750), 750)
})

test('total runtime is the narration plus one tail per scene', () => {
  const scenes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
  const seconds = { a: 10, b: 20, c: 5 }
  assert.equal(estimateTotalSeconds(scenes, seconds, { tailMs: 1000 }), 38)
})

test('the outro hold counts towards the total', () => {
  const total = estimateTotalSeconds([{ id: 'a' }], { a: 10 }, { tailMs: 0, outroMs: 3500 })
  assert.equal(total, 13.5)
})

test('spoken length tracks word count at a narration pace', () => {
  const words = n => Array.from({ length: n }, () => 'word').join(' ')
  // 165 wpm: 165 words should land on about a minute.
  assert.ok(Math.abs(estimateSpokenSeconds(words(165)) - 60) < 0.01)
  assert.ok(estimateSpokenSeconds(words(60)) > estimateSpokenSeconds(words(30)))
})

test('a very short line still gets enough time to be read', () => {
  assert.equal(estimateSpokenSeconds('Hello there'), 1.5)
})

test('empty narration is zero, not the floor', () => {
  assert.equal(estimateSpokenSeconds(''), 0)
  assert.equal(estimateSpokenSeconds('   '), 0)
  assert.equal(estimateSpokenSeconds(null), 0)
})
