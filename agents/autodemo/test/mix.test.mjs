import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildFilterComplex, buildFfmpegArgs } from '../src/engine/mix.mjs'

test('filter indexes audio inputs from 1, because input 0 is the video', () => {
  const f = buildFilterComplex([0, 5000, 12345])
  assert.match(f, /\[1:a\]adelay=0:all=1\[d0\]/)
  assert.match(f, /\[2:a\]adelay=5000:all=1\[d1\]/)
  assert.match(f, /\[3:a\]adelay=12345:all=1\[d2\]/)
})

test('filter chains every delayed clip into one amix', () => {
  const f = buildFilterComplex([0, 1000, 2000, 3000])
  assert.match(f, /\[d0\]\[d1\]\[d2\]\[d3\]amix=inputs=4/)
})

test('amix does not renormalise and does not duck on dropout', () => {
  // normalize=1 would quietly halve the volume the moment two clips overlap;
  // dropout_transition would fade the bed between scenes.
  const f = buildFilterComplex([0, 1000])
  assert.match(f, /normalize=0/)
  assert.match(f, /dropout_transition=0/)
})

test('filter apads so the audio graph outlives the last clip', () => {
  assert.match(buildFilterComplex([0]), /,apad\[mix\]$/)
})

test('marks are rounded and clamped to zero', () => {
  const f = buildFilterComplex([-40, 1000.7])
  assert.match(f, /adelay=0:all=1\[d0\]/)
  assert.match(f, /adelay=1001:all=1\[d1\]/)
})

test('an empty mark list is rejected rather than producing a broken filter', () => {
  assert.throws(() => buildFilterComplex([]), /at least one mark/)
})

test('ffmpeg args map video from input 0 and audio from the mix', () => {
  const args = buildFfmpegArgs({
    videoFile: 'raw.webm', audioFiles: ['a.mp3', 'b.mp3'], marksMs: [0, 4000],
    videoDuration: 31.5, outFile: 'out.mp4', crf: 23, preset: 'fast',
  })
  const at = flag => args[args.indexOf(flag) + 1]
  assert.equal(args[0], '-y')
  assert.deepEqual(args.slice(1, 3), ['-i', 'raw.webm'])
  assert.equal(args.filter(a => a === '-i').length, 3)       // 1 video + 2 audio
  assert.deepEqual([at('-map'), args[args.lastIndexOf('-map') + 1]], ['0:v:0', '[mix]'])
  assert.equal(at('-t'), '31.5')
  assert.equal(at('-crf'), '23')
  assert.equal(at('-preset'), 'fast')
  assert.equal(args.at(-1), 'out.mp4')
})

test('ffmpeg args force even dimensions and a universally-playable profile', () => {
  const args = buildFfmpegArgs({
    videoFile: 'v.webm', audioFiles: ['a.mp3'], marksMs: [0],
    videoDuration: 10, outFile: 'o.mp4',
  })
  const at = flag => args[args.indexOf(flag) + 1]
  assert.equal(at('-vf'), 'scale=trunc(iw/2)*2:trunc(ih/2)*2')
  assert.equal(at('-pix_fmt'), 'yuv420p')
  assert.equal(at('-c:v'), 'libx264')
  assert.equal(at('-c:a'), 'aac')
  assert.equal(at('-movflags'), '+faststart')
})

test('a clip/mark count mismatch fails loudly instead of silently dropping audio', () => {
  assert.throws(() => buildFfmpegArgs({
    videoFile: 'v', audioFiles: ['a', 'b'], marksMs: [0],
    videoDuration: 1, outFile: 'o.mp4',
  }), /same length/)
})
